# macromolecules/tasks.py
import os
import shlex
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Tuple, List, Optional

from celery import shared_task
from celery.utils.log import get_task_logger
from django.db import transaction

from macromolecules.util import textfld
from macromolecules.models import Macromolecule

logger = get_task_logger(__name__)

# ====== Caminhos das ferramentas (override por ENV) ======
PYTHONSH = os.getenv("PYTHONSH_PATH", "/home/autodockgpu/mgltools_x86_64Linux2_1.5.7/bin/pythonsh")
PREPARE_RECEPTOR = os.getenv("PREPARE_RECEPTOR4_PATH", "/home/autodockgpu/mgltools_x86_64Linux2_1.5.7/MGLToolsPckgs/AutoDockTools/Utilities24/prepare_receptor4.py")
PREPARE_LIGAND = os.getenv("PREPARE_LIGAND4_PATH", "/home/autodockgpu/mgltools_x86_64Linux2_1.5.7/MGLToolsPckgs/AutoDockTools/Utilities24/prepare_ligand4.py")
PREPARE_GPF = os.getenv("PREPARE_GPF4_PATH", "/home/autodockgpu/mgltools_x86_64Linux2_1.5.7/MGLToolsPckgs/AutoDockTools/Utilities24/prepare_gpf4.py")
AUTOGRID4_BIN = os.getenv("AUTOGRID4_BIN", "/home/autodockgpu/x86_64Linux2/autogrid4")
AD4_PARAMETERS_DAT = os.getenv("AD4_PARAMETERS_DAT", "/home/autodockgpu/x86_64Linux2/AD4_parameters.dat")
AUTODOCK_GPU_BIN = os.getenv("AUTODOCK_GPU_BIN", "/home/autodockgpu/AutoDock-GPU/bin/autodock_gpu_128wi")

FLD_APPEND_CUTOFF_LINE = int(os.getenv("FLD_APPEND_CUTOFF_LINE", "23"))

# ====== Grupos de tipos de ligantes ======
LIGAND_GROUPS: List[str] = [
    "C,A,N,NA,NS,OA,OS,SA,S,H,HD",
    "HS,P,Br,BR,Ca,CA,Cl,CL,F,Fe,FE",
    "I,Mg,MG,Mn,MN,Zn,ZN,He,Li,Be",
    "B,Ne,Na,Al,Si,K,Sc,Ti,V,Co",
    "Ni,Cu,Ga,Ge,As,Se,Kr,Rb,Sr,Y",
    "Zr,Nb,Cr,Tc,Ru,Rh,Pd,Ag,Cd,In",
    "Sn,Sb,Te,Xe,Cs,Ba,La,Ce,Pr,Nd",
    "Pm,Sm,Eu,Gd,Tb,Dy,Ho,Er,Tm,Yb",
    "Lu,Hf,Ta,W,Re,Os,Ir,Pt,Au,Hg",
    "Tl,Pb,Bi,Po,At,Rn,Fr,Ra,Ac,Th",
    "Pa,U,Np,Pu,Am,Cm,Bk,Cf,E,Fm",
]

# ====== Exec helpers (sem arquivos auxiliares) ======
def _run(cmd: List[str], workdir: Path, tag: str) -> None:
    cmd_str = " ".join(shlex.quote(c) for c in cmd)
    logger.info("[%s] running: %s (cwd=%s)", tag, cmd_str, workdir)
    proc = subprocess.run(cmd, cwd=str(workdir), text=True, capture_output=True)
    if proc.stdout:
        logger.info("[%s][stdout]\n%s", tag, proc.stdout.strip())
    if proc.stderr:
        logger.warning("[%s][stderr]\n%s", tag, proc.stderr.strip())
    if proc.returncode != 0:
        logger.error("[%s] failed with rc=%s", tag, proc.returncode)
        raise RuntimeError(f"{tag} failed (rc={proc.returncode})")
    logger.info("[%s] done (rc=0)", tag)

def _run_capture(cmd: List[str], workdir: Path, tag: str) -> str:
    cmd_str = " ".join(shlex.quote(c) for c in cmd)
    logger.info("[%s] running: %s (cwd=%s)", tag, cmd_str, workdir)
    proc = subprocess.run(cmd, cwd=str(workdir), text=True, capture_output=True)
    if proc.stderr:
        logger.warning("[%s][stderr]\n%s", tag, proc.stderr.strip())
    if proc.returncode != 0:
        logger.error("[%s] failed with rc=%s", tag, proc.returncode)
        raise RuntimeError(f"{tag} failed (rc={proc.returncode})")
    logger.info("[%s] done (rc=0)", tag)
    return proc.stdout or ""

def _parse_triplet_int(s: Optional[str]) -> Optional[Tuple[int, int, int]]:
    if not s: return None
    parts = [p for p in s.replace(",", " ").split() if p]
    if len(parts) != 3:
        raise ValueError("gridsize deve ter 3 inteiros (ex.: '60 60 60')")
    return int(parts[0]), int(parts[1]), int(parts[2])

def _parse_triplet_float(s: Optional[str]) -> Optional[Tuple[float, float, float]]:
    if not s: return None
    parts = [p for p in s.replace(",", " ").split() if p]
    if len(parts) != 3:
        raise ValueError("gridcenter deve ter 3 floats (ex.: '15.5 20.3 10.2')")
    return float(parts[0]), float(parts[1]), float(parts[2])

def _calculate_ligand_center(ligand_path: Path) -> Optional[Tuple[float, float, float]]:
    try:
        n = 0; sx = sy = sz = 0.0
        with ligand_path.open("r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if line.startswith(("ATOM", "HETATM")) and len(line) >= 54:
                    x = float(line[30:38]); y = float(line[38:46]); z = float(line[46:54])
                    n += 1; sx += x; sy += y; sz += z
        if n > 0:
            center = (sx/n, sy/n, sz/n)
            logger.info("[center] computed from ligand %s: %s", ligand_path.name, center)
            return center
        logger.warning("[center] no ATOM/HETATM coords found in %s", ligand_path.name)
        return None
    except Exception as e:
        logger.exception("[center] error computing center from %s: %s", ligand_path, e)
        return None

def _prepend_parameter_file(gpf_path: Path, parameter_file: str):
    text = gpf_path.read_text(encoding="utf-8")
    gpf_path.write_text(f"parameter_file {parameter_file}\n{text}", encoding="utf-8")
    logger.info("[gpf] parameter_file added to %s", gpf_path.name)

def _postprocess_fld(fld_path: Path, receptor_name: str):
    if not fld_path.exists():
        logger.error("[fld] %s not found", fld_path); return
    lines = fld_path.read_text(encoding="utf-8").splitlines(keepends=True)
    keep = lines[:FLD_APPEND_CUTOFF_LINE] if len(lines) >= FLD_APPEND_CUTOFF_LINE else lines
    tpl = textfld()
    extra = tpl.replace("kakakakaka", receptor_name)
    with fld_path.open("w", encoding="utf-8") as f:
        f.writelines(keep); f.write(extra)
    logger.info("[fld] postprocessed %s (cut to %d lines + template)", fld_path.name, FLD_APPEND_CUTOFF_LINE)

def _extract_xml_from_text(text: str) -> Optional[str]:
    start = text.find("<?xml")
    end_tag = "</autodock_gpu>"
    end = text.rfind(end_tag)
    if start != -1 and end != -1:
        return text[start:end + len(end_tag)]
    return None

def _parse_best_from_xml(xml_text: str) -> Optional[Tuple[float, float]]:
    """Retorna (best_reference_rmsd, corresponding_binding_energy) do XML do AutoDock-GPU."""
    try:
        root = ET.fromstring(xml_text)
        runs = root.findall(".//result/rmsd_table/run")
        best = None  # (rmsd, be)
        for r in runs:
            rmsd = float(r.attrib.get("reference_rmsd"))
            be = float(r.attrib.get("binding_energy"))
            if best is None or rmsd < best[0]:
                best = (rmsd, be)
        return best
    except Exception as e:
        logger.exception("[xml] failed to parse autodock_gpu XML: %s", e)
        return None


# ====== Task principal ======
@shared_task(bind=True)
def prepare_macromolecule(
    self,
    workdir: str,
    receptor_filename: str,
    gridsize: Optional[str] = None,
    gridcenter: Optional[str] = None,
    ligand_filename: Optional[str] = None,
    macromolecule_id: Optional[str] = None,   # ← opcional; retrocompatível
) -> dict:
    wd = Path(workdir)
    wd.mkdir(parents=True, exist_ok=True)

    receptor_name = Path(receptor_filename).stem
    receptor_pdb = wd / receptor_filename
    receptor_pdbqt = wd / f"{receptor_name}.pdbqt"

    logger.info("=== prepare_macromolecule ===")
    logger.info("[ctx] workdir=%s", wd)
    logger.info("[ctx] receptor=%s", receptor_pdb.name)
    if ligand_filename: logger.info("[ctx] ligand=%s", ligand_filename)
    if gridsize: logger.info("[ctx] gridsize=%s", gridsize)
    if gridcenter: logger.info("[ctx] gridcenter=%s", gridcenter)

    # 0) ferramentas
    must_exist = {
        "pythonsh": Path(PYTHONSH),
        "prepare_receptor4.py": Path(PREPARE_RECEPTOR),
        "prepare_gpf4.py": Path(PREPARE_GPF),
        "autogrid4": Path(AUTOGRID4_BIN),
        "AD4_parameters.dat": Path(AD4_PARAMETERS_DAT),
        "autodock_gpu": Path(AUTODOCK_GPU_BIN),
    }
    missing = [k for k, p in must_exist.items() if not p.exists()]
    if missing:
        logger.error("[tools] missing: %s", ", ".join(missing))
        raise RuntimeError(f"Ferramentas ausentes: {', '.join(missing)}")
    logger.info("[tools] ok")

    # 1) receptor -> pdbqt
    if not receptor_pdb.exists():
        raise FileNotFoundError(f"Receptor .pdb não está em {receptor_pdb}")
    _run([PYTHONSH, PREPARE_RECEPTOR, "-r", receptor_pdb.name, "-o", f"{receptor_name}.pdbqt", "-A", "hydrogens"],
         wd, f"{receptor_name}.prepare_receptor4")
    if not receptor_pdbqt.exists():
        raise RuntimeError("prepare_receptor4 não gerou o .pdbqt do receptor")

    # 2) GPFs
    size_t = _parse_triplet_int(gridsize) if gridsize else None
    center_t = _parse_triplet_float(gridcenter) if gridcenter else None

    ligand_pdb = wd / ligand_filename if ligand_filename else None
    if center_t is None and ligand_pdb and ligand_pdb.exists():
        center_t = _calculate_ligand_center(ligand_pdb)
        if center_t is None:
            raise RuntimeError("Não foi possível calcular o centro a partir do ligante")

    if size_t is None or center_t is None:
        raise RuntimeError("gridsize e gridcenter são obrigatórios (ou calcule center via ligante)")

    gpf_files: List[Path] = []
    for i, ligand_types in enumerate(LIGAND_GROUPS, start=1):
        gpf_name = f"grid_{i}.gpf"
        _run(
            [PYTHONSH, PREPARE_GPF, "-r", receptor_pdbqt.name, "-o", gpf_name,
             "-p", f"gridcenter={center_t[0]},{center_t[1]},{center_t[2]}",
             "-p", f"npts={size_t[0]},{size_t[1]},{size_t[2]}",
             "-p", f"ligand_types={ligand_types}"],
            wd, f"{receptor_name}.prepare_gpf4.{i}"
        )
        gpf_path = wd / gpf_name
        if not gpf_path.exists():
            raise RuntimeError(f"Falha ao gerar {gpf_name}")
        _prepend_parameter_file(gpf_path, AD4_PARAMETERS_DAT)
        gpf_files.append(gpf_path)

    # 3) autogrid4
    for i, gpf in enumerate(gpf_files, start=1):
        _run([AUTOGRID4_BIN, "-p", gpf.name, "-l", f"grid_{i}.glg"], wd, f"{receptor_name}.autogrid4.{i}")

    fld_candidates = list(wd.glob("*.maps.fld"))
    if not fld_candidates:
        raise RuntimeError("Nenhum arquivo *.maps.fld gerado por autogrid4")
    fld_path = fld_candidates[0]

    # 4) pós-processo fld
    _postprocess_fld(fld_path, receptor_name)

    # 5) (opcional) ligante -> pdbqt
    ligand_pdbqt = None
    if ligand_pdb and ligand_pdb.exists():
        ligand_name = ligand_pdb.stem
        ligand_pdbqt = wd / f"{ligand_name}.pdbqt"
        _run([PYTHONSH, PREPARE_LIGAND, "-l", ligand_pdb.name, "-o", ligand_pdbqt.name],
             wd, f"{ligand_name}.prepare_ligand4")
        if not ligand_pdbqt.exists():
            raise RuntimeError("prepare_ligand4 não gerou o .pdbqt do ligante")

    # 6) AutoDock-GPU + parse XML (apenas se houver ligante preparado)
    docking_ran = False
    best_reference_rmsd: Optional[float] = None
    best_binding_energy: Optional[float] = None
    docking_xml_path: Optional[Path] = None

    if ligand_pdbqt and ligand_pdbqt.exists():
        stdout_xml = _run_capture(
            [AUTODOCK_GPU_BIN, "--ffile", fld_path.name, "--lfile", ligand_pdbqt.name],
            wd, f"{ligand_pdbqt.stem}.autodock_gpu"
        )
        docking_ran = True

        xml_text = _extract_xml_from_text(stdout_xml)
        if not xml_text:
            candidates = sorted(wd.glob("*.xml"))
            if candidates:
                try:
                    xml_text = candidates[-1].read_text(encoding="utf-8")
                    docking_xml_path = candidates[-1]
                except Exception:
                    xml_text = None

        if xml_text and docking_xml_path is None:
            docking_xml_path = wd / "docking_result.xml"
            docking_xml_path.write_text(xml_text, encoding="utf-8")

        if xml_text:
            best = _parse_best_from_xml(xml_text)
            if best:
                best_reference_rmsd, best_binding_energy = best
                logger.info("[autodock-gpu] best reference_rmsd=%.3f, binding_energy=%.2f",
                            best_reference_rmsd, best_binding_energy)
        else:
            logger.warning("[autodock-gpu] nenhum XML encontrado")

    else:
        logger.warning("[autodock-gpu] skipped: ligand .pdbqt not available")

    # 7) === ATUALIZA DB ===
    db_updated = False
    try:
        with transaction.atomic():
            obj = Macromolecule.objects.select_related("type").filter(id=macromolecule_id).first()
            if obj:
                obj.rmsd_redocking = f"{best_reference_rmsd:.3f}" if best_reference_rmsd is not None else obj.rmsd_redocking
                obj.energia_original = f"{best_binding_energy:.2f}" if best_binding_energy is not None else obj.energia_original
                # opcional: guardar o caminho do .fld; se preferir manter a pasta, deixe como estava
                obj.pathFilefld = str(fld_path) if fld_path else obj.pathFilefld
                obj.save(update_fields=["rmsd_redocking", "energia_original", "pathFilefld"])
    except Exception:
        # Logue mas não quebre o retorno da task
        import logging
        logging.getLogger(__name__).exception("[db] failed to update macromolecule")

    logger.info("=== prepare_macromolecule OK ===")
    return {
        "ok": True,
        "workdir": str(wd),
        "receptor_pdb": receptor_pdb.name,
        "receptor_pdbqt": receptor_pdbqt.name,
        "fld": fld_path.name,
        "gpf_count": len(gpf_files),
        "ligand_pdb": ligand_pdb.name if ligand_pdb and ligand_pdb.exists() else None,
        "ligand_pdbqt": ligand_pdbqt.name if ligand_pdbqt and ligand_pdbqt.exists() else None,
        "gridcenter": center_t,
        "gridsize": size_t,
        "docking_ran": docking_ran,
        "docking_xml": str(docking_xml_path) if docking_xml_path else None,
        "best_reference_rmsd": best_reference_rmsd,
        "best_binding_energy": best_binding_energy,
        "db_updated": db_updated,
        "macromolecule_id": macromolecule_id,
    }
