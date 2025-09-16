# processes/tasks.py
import csv
import json
import logging
import os
import time
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import xml.etree.ElementTree as ET

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from macromolecules.models import Macromolecule
from processes.models import Process, ProcessStatusEnum

logger = logging.getLogger(__name__)

# Caminhos das ferramentas (podem ser sobrescritos por ENV no worker)
AUTO_DOCK_GPU = os.getenv("AUTODOCK_GPU_BIN", "/home/autodockgpu/AutoDock-GPU/bin/autodock_gpu_128wi")
OBABEL_BIN     = os.getenv("OBABEL_BIN", "/usr/bin/obabel")


# ===== Helpers =====
def run_cmd(cmd: List[str], cwd: Path, timeout: int = 600) -> str:
    """Executa comando de sistema, logando stdout/stderr (prévia)."""
    import subprocess
    t0 = time.time()
    logger.info("[$] %s  (cwd=%s)", " ".join(cmd), cwd)
    try:
        res = subprocess.run(cmd, cwd=str(cwd), text=True,
                             capture_output=True, check=True, timeout=timeout)
        dt = time.time() - t0
        out_preview = (res.stdout or "")[:300]
        err_preview = (res.stderr or "")[:300]
        logger.debug("[OK %.1fs] stdout: %r | stderr: %r", dt, out_preview, err_preview)
        return res.stdout
    except subprocess.TimeoutExpired:
        logger.error("[TIMEOUT %ss] cmd: %s", timeout, " ".join(cmd))
        raise
    except subprocess.CalledProcessError as e:
        dt = time.time() - t0
        logger.error("[ERR %.1fs] rc=%s | stderr: %r", dt, e.returncode, (e.stderr or "")[:500])
        raise


def ensure_exists(path: Path, is_file: bool = False):
    if is_file:
        if not path.exists():
            raise FileNotFoundError(f"Arquivo não encontrado: {path}")
    else:
        path.mkdir(parents=True, exist_ok=True)


# ===== Split de SDF em PDBQT (OpenBabel) =====
def split_sdf_to_pdbqt(sdf_file: Path, out_dir: Path) -> List[Path]:
    """Converte um SDF multi-moléculas em vários .pdbqt no diretório out_dir."""
    ensure_exists(out_dir, is_file=False)
    # Gera arquivos numerados: ligand1.pdbqt, ligand2.pdbqt, ...
    cmd = [OBABEL_BIN, "-isdf", str(sdf_file), "-opdbqt", "--split"]
    run_cmd(cmd, cwd=out_dir, timeout=1800)  # até 30min para SDFs grandes
    files = sorted(out_dir.glob("*.pdbqt"))
    logger.info("OpenBabel gerou %d ligantes .pdbqt", len(files))
    return files


# ===== Extração de melhor energia / rmsd do XML do AutoDock-GPU =====
def extract_best_from_xml(xml_path: Path) -> Tuple[float, float, int]:
    """
    Lê o XML do AutoDock-GPU e retorna:
      (binding_energy_correspondente_ao_menor_reference_rmsd, menor_reference_rmsd, run_id)
    """
    ensure_exists(xml_path, is_file=True)
    root = ET.parse(xml_path).getroot()
    rmsd_table = root.find(".//rmsd_table")
    if rmsd_table is None:
        raise ValueError(f"<rmsd_table> não encontrado em {xml_path.name}")

    best_rmsd: Optional[float] = None
    best_energy: Optional[float] = None
    best_run: Optional[int] = None

    for run_el in rmsd_table.findall("run"):
        try:
            rmsd = float(run_el.get("reference_rmsd"))
            energy = float(run_el.get("binding_energy"))
            run_id = int(run_el.get("run"))
        except (TypeError, ValueError):
            continue

        if best_rmsd is None or rmsd < best_rmsd:
            best_rmsd = rmsd
            best_energy = energy
            best_run = run_id

    if best_rmsd is None or best_energy is None or best_run is None:
        raise ValueError(f"Nenhum run válido em {xml_path.name}")

    return best_energy, best_rmsd, best_run


# ===== Execução do AutoDock-GPU =====
def run_autodock_gpu(fld_file: Path, ligand_pdbqt: Path, out_prefix: Path) -> Path:
    """
    Executa o AutoDock-GPU:
      autodock_gpu_128wi --ffile receptor.maps.fld --lfile lig.pdbqt --gbest 1 --resnam <out_prefix>
    Retorna o caminho do XML gerado (<out_prefix>.xml).
    """
    ensure_exists(fld_file, is_file=True)
    ensure_exists(ligand_pdbqt, is_file=True)
    ensure_exists(out_prefix.parent, is_file=False)

    cmd = [
        AUTO_DOCK_GPU,
        "--ffile", str(fld_file),
        "--lfile", str(ligand_pdbqt),
        "--gbest", "1",
        "--resnam", str(out_prefix)
    ]
    run_cmd(cmd, cwd=fld_file.parent, timeout=3600)  # até 1h

    xml_path = Path(str(out_prefix) + ".xml")
    ensure_exists(xml_path, is_file=True)
    return xml_path


# ===== Estrutura de diretórios do processo =====
def prepare_process_dirs(sdf_path: Path, process_id: str) -> Dict[str, Path]:
    """
    Cria (se necessário) uma pasta por processo ao lado do SDF:
      <SDF_DIR>/process_<id>/{ligantes_pdbqt, arquivos_dlgs, gbest_pdb, logs}
    """
    base = sdf_path.parent
    lig_dir = base / "ligantes_pdbqt"
    dlgs   = base / "arquivos_dlgs"
    gbest  = base / "gbest_pdb"
    logs   = base / "logs"

    for d in (base, lig_dir, dlgs, gbest, logs):
        d.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(d, 0o2775)  # herança de grupo, rwx para user/group
        except PermissionError:
            pass

    return {
        "base": base,
        "ligantes_pdbqt": lig_dir,
        "arquivos_dlgs": dlgs,
        "gbest_pdb": gbest,
        "logs": logs,
    }


# ===== Seleção de macromoléculas =====
def get_macromolecules_for_process(proc: Process) -> List[Macromolecule]:
    """
    Busca macromoléculas do mesmo 'type' do processo (ordenadas por 'rec').
    """
    return list(Macromolecule.objects.filter(type=proc.type).order_by("rec"))


# ===== CSV simples =====
def write_rows_csv(csv_path: Path, rows: List[Dict]):
    if not rows:
        # Cria CSV vazio com headers mínimos mesmo sem dados
        with csv_path.open("w", encoding="utf-8", newline="") as f:
            headers = ["PROCESS_ID", "TYPE", "RECEPTOR_REC", "LIGAND_FILE", 
                      "BEST_BINDING_ENERGY", "BEST_REFERENCE_RMSD", "BEST_RUN", "ERROR"]
            w = csv.DictWriter(f, fieldnames=headers, delimiter=";")
            w.writeheader()
        return
        
    headers = sorted({k for r in rows for k in r.keys()})
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=headers, delimiter=";")
        w.writeheader()
        for r in rows:
            w.writerow(r)


# ===== ZIP do resultado =====
def zip_tree(folder: Path, zip_path: Path):
    try:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
            for p in folder.rglob("*"):
                if p.is_file():
                    z.write(p, p.relative_to(folder))
    except Exception as e:
        logger.warning("Erro ao criar ZIP: %s", e)


# ===== Tarefa Celery principal =====
@shared_task(name="processes.run_plasmodocking_process")
def run_plasmodocking_process(process_id: str) -> dict:
    """
    Executa o pipeline do 'Process':
      - valida SDF
      - split em PDBQT
      - para cada Macromolecule do type, roda AutoDock-GPU com cada ligante
      - extrai melhor (menor) reference_rmsd e binding_energy correspondente
      - salva JSON/CSV/ZIP
      - atualiza Process.resultado_final e status
    
    IMPORTANTE: Erros em moléculas/ligantes individuais não abortam o processo.
    """
    t_all = time.time()
    logger.info("🚀 Iniciando processo %s", process_id)

    # Carrega o processo
    try:
        proc = Process.objects.select_related("type").get(id=process_id)
    except Process.DoesNotExist:
        logger.error("Processo %s não encontrado", process_id)
        return {"ok": False, "error": "process_not_found"}

    # Atualiza status -> PROCESSANDO
    with transaction.atomic():
        proc.status = ProcessStatusEnum.PROCESSANDO
        proc.updated_at = timezone.now()
        proc.save(update_fields=["status", "updated_at"])

    # Valida ferramentas globais (erros globais abortam)
    for name, p in [("autodock_gpu", Path(AUTO_DOCK_GPU)), ("obabel", Path(OBABEL_BIN))]:
        if not p.exists():
            msg = f"{name} não encontrado em {p}"
            logger.error(msg)
            _fail_process(proc, msg)
            return {"ok": False, "error": msg}

    # Valida SDF (erro global aborta)
    sdf_path = Path(proc.pathFileSDF)
    if not sdf_path.is_absolute():
        sdf_path = Path.cwd() / sdf_path
    if not sdf_path.exists():
        msg = f"SDF não encontrado: {sdf_path}"
        logger.error(msg)
        _fail_process(proc, msg)
        return {"ok": False, "error": msg}

    # Prepara diretórios
    paths = prepare_process_dirs(sdf_path, str(proc.id))
    lig_dir = paths["ligantes_pdbqt"]
    dlgs_dir = paths["arquivos_dlgs"]
    gbest_dir = paths["gbest_pdb"]

    # Split SDF -> PDBQT (erro global aborta)
    try:
        ligands = split_sdf_to_pdbqt(sdf_path, lig_dir)
    except Exception as e:
        _fail_process(proc, f"Falha no OpenBabel: {e}")
        return {"ok": False, "error": str(e)}

    macs = get_macromolecules_for_process(proc)
    logger.info("Processo %s: %d macromoléculas; %d ligantes", proc.id, len(macs), len(ligands))
    if not macs or not ligands:
        msg = "Sem macromoléculas ou ligantes para processar"
        _fail_process(proc, msg)
        return {"ok": False, "error": msg}

    # -------- Loop principal com tolerância a erros por receptor/ligante --------
    macs_results: List[Dict] = []
    csv_rows: List[Dict] = []
    
    # Contadores globais para estatísticas
    total_combinations = len(macs) * len(ligands)
    successful_combinations = 0
    failed_combinations = 0
    skipped_receptors = 0

    for m in macs:
        rec_block: Dict = {
            "macromolecule_id": str(m.id),
            "receptor_rec": m.rec.upper(),
            "receptor_nome": m.nome,
            "grid_size": m.gridsize,
            "grid_center": m.gridcenter,
            "fld": m.pathFilefld,
            "ligantes": [],
            "status": "processing",  # novo campo de status
        }
        if m.type.redocking:
            rec_block.update({
                "rmsd_redocking": m.rmsd_redocking,
                "ligante_original": m.ligante_original,
                "energia_original": m.energia_original,
            })
        # Resolve path do fld (*.maps.fld) por receptor
        try:
            fld_path = Path(m.pathFilefld)
            if fld_path.is_dir():
                found = list(fld_path.glob("*.maps.fld"))
                if not found:
                    raise FileNotFoundError(f"Nenhum .maps.fld encontrado em {fld_path}")
                fld_path = found[0]
            if not fld_path.exists():
                raise FileNotFoundError(f"Arquivo .maps.fld não existe: {fld_path}")
        except Exception as e:
            # ❗️Erro POR MACROMOLÉCULA (não aborta processo)
            rec_block["error"] = f"fld_error: {e}"
            rec_block["status"] = "error"
            rec_block["ligantes_ok"] = 0
            rec_block["ligantes_failed"] = len(ligands)
            macs_results.append(rec_block)
            skipped_receptors += 1
            failed_combinations += len(ligands)
            
            # Adiciona linhas de erro no CSV para cada ligante que não foi processado
            for lig in ligands:
                csv_rows.append({
                    "PROCESS_ID": str(proc.id),
                    "TYPE": m.type.name if m.type else "",
                    "RECEPTOR_REC": m.rec,
                    "LIGAND_FILE": lig.name,
                    "ERROR": f"Receptor error: {e}",
                })
            
            logger.warning("⚠️ Receptor %s ignorado: %s", m.rec, e)
            continue

        ok_ligs = 0
        failed_ligs = 0
        
        for lig in ligands:
            out_prefix = dlgs_dir / f"{lig.stem}_{m.rec}"
            lig_result = {"ligand": lig.name}
            
            try:
                # Executa AutoDock-GPU
                xml_path = run_autodock_gpu(fld_path, lig, out_prefix)
                
                # Extrai melhores resultados
                best_energy, best_rmsd, best_run = extract_best_from_xml(xml_path)
                
                ok_ligs += 1
                successful_combinations += 1

                lig_result.update({
                    "best_binding_energy": best_energy,
                    "best_reference_rmsd": best_rmsd,
                    "best_run": best_run,
                    "xml": str(xml_path),
                    "status": "success",
                })

                csv_rows.append({
                    "PROCESS_ID": str(proc.id),
                    "TYPE": m.type.name if m.type else "",
                    "RECEPTOR_REC": m.rec,
                    "LIGAND_FILE": lig.name,
                    "BEST_BINDING_ENERGY": best_energy,
                    "BEST_REFERENCE_RMSD": best_rmsd,
                    "BEST_RUN": best_run,
                })

                # Move melhores saídas combinadas (se existirem)
                try:
                    for cand in out_prefix.parent.glob(f"{out_prefix.name}*.pdbqt"):
                        dest = gbest_dir / cand.name
                        cand.replace(dest)
                except Exception as mv_err:
                    logger.debug("Erro ao mover arquivo gbest: %s", mv_err)

            except Exception as e:
                # ❗️Erro POR LIGANTE (não aborta receptor/processo)
                failed_ligs += 1
                failed_combinations += 1
                
                error_msg = str(e)
                logger.warning("⚠️ Ligante %s falhou em %s: %s", lig.name, m.rec, error_msg)
                
                lig_result.update({
                    "error": error_msg,
                    "status": "error",
                })
                
                # Adiciona linha de erro no CSV
                csv_rows.append({
                    "PROCESS_ID": str(proc.id),
                    "TYPE": m.type.name if m.type else "",
                    "RECEPTOR_REC": m.rec,
                    "LIGAND_FILE": lig.name,
                    "ERROR": error_msg,
                })
            
            rec_block["ligantes"].append(lig_result)

        # Atualiza estatísticas do receptor
        rec_block["ligantes_ok"] = ok_ligs
        rec_block["ligantes_failed"] = failed_ligs
        rec_block["status"] = "completed" if ok_ligs > 0 else "failed"
        macs_results.append(rec_block)

    # -------- Determinação do status final do processo --------
    total_time = time.time() - t_all
    
    # Define status baseado nos resultados
    if successful_combinations == 0:
        # Nenhuma combinação funcionou
        final_status = ProcessStatusEnum.ERROR
        status_msg = "FALHA TOTAL: Nenhuma combinação receptor-ligante foi processada com sucesso"
    elif successful_combinations == total_combinations:
        # Todas as combinações funcionaram
        final_status = ProcessStatusEnum.CONCLUIDO
        status_msg = "SUCESSO COMPLETO: Todas as combinações foram processadas"
    else:
        # Sucesso parcial
        final_status = ProcessStatusEnum.CONCLUIDO
        status_msg = f"SUCESSO PARCIAL: {successful_combinations}/{total_combinations} combinações processadas"

    # -------- Persistência dos artefatos --------
    results_payload = {
        "ok": successful_combinations > 0,
        "process_id": str(proc.id),
        "elapsed_sec": total_time,
        "status_message": status_msg,
        "statistics": {
            "total_combinations": total_combinations,
            "successful_combinations": successful_combinations,
            "failed_combinations": failed_combinations,
            "skipped_receptors": skipped_receptors,
            "total_receptors": len(macs),
            "total_ligands": len(ligands),
            "success_rate": f"{(successful_combinations/total_combinations*100):.2f}%" if total_combinations > 0 else "0%",
        },
        "macromolecules": macs_results,
    }

    # Salva JSON
    json_path = paths["base"] / "resultado.json"
    try:
        json_path.write_text(json.dumps(results_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("✅ JSON salvo: %s", json_path)
    except Exception as e:
        logger.error("Erro ao salvar JSON: %s", e)

    # Salva CSV
    csv_path = paths["base"] / "resultado.csv"
    try:
        write_rows_csv(csv_path, csv_rows)
        logger.info("✅ CSV salvo: %s", csv_path)
    except Exception as e:
        logger.error("Erro ao salvar CSV: %s", e)

    # Cria ZIP
    zip_path = paths["base"] / f"{paths['base'].name}.zip"
    try:
        zip_tree(paths["base"], zip_path)
        logger.info("✅ ZIP criado: %s", zip_path)
    except Exception as e:
        logger.error("Erro ao criar ZIP: %s", e)
        zip_path = None

    # Atualiza Process com resultado final
    with transaction.atomic():
        proc.resultado_final = results_payload
        proc.status = final_status
        proc.updated_at = timezone.now()
        proc.pathFileZIP = str(zip_path) if zip_path else None  
        proc.save(update_fields=["resultado_final", "status", "updated_at", "pathFileZIP"])

    logger.info(
        "🎉 Processo %s finalizado em %.1fs | Status: %s | Sucesso: %d/%d | json=%s | csv=%s | zip=%s",
        proc.id, total_time, status_msg, successful_combinations, total_combinations,
        json_path, csv_path, zip_path or "N/A"
    )

    return {
        "ok": successful_combinations > 0,
        "process_id": str(proc.id),
        "status": status_msg,
        "statistics": results_payload["statistics"],
        "json": str(json_path),
        "csv": str(csv_path),
        "zip": str(zip_path) if zip_path else None,
        "elapsed_sec": total_time,
    }


def _fail_process(proc: Process, msg: str):
    """Marca processo como ERROR e salva mensagem no resultado_final"""
    with transaction.atomic():
        proc.status = ProcessStatusEnum.ERROR
        proc.resultado_final = {
            "ok": False,
            "error": msg,
            "process_id": str(proc.id),
            "timestamp": timezone.now().isoformat(),
        }
        proc.updated_at = timezone.now()
        proc.save(update_fields=["status", "resultado_final", "updated_at"])
    logger.error("❌ Processo %s marcado como ERROR: %s", proc.id, msg)


def _fail_and_dict(proc: Process, msg: str) -> dict:
    """Helper para falhar processo e retornar dict de erro"""
    _fail_process(proc, msg)
    return {"ok": False, "error": msg, "process_id": str(proc.id)}