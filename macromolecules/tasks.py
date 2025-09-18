"""
Módulo de processamento assíncrono de macromoléculas para docking molecular.
Utiliza Celery para execução de tarefas de preparação de receptores e ligantes.
"""
import os
import shlex
import subprocess
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Tuple, List, Optional, Dict, Any
from functools import lru_cache

from celery import shared_task
from celery.utils.log import get_task_logger
from django.db import transaction

from macromolecules.util import textfld
from macromolecules.models import Macromolecule

logger = get_task_logger(__name__)

# ====== Configuração de caminhos (com cache) ======
@dataclass(frozen=True)
class ToolPaths:
    """Centraliza todos os caminhos de ferramentas com validação."""
    pythonsh: Path
    prepare_receptor: Path
    prepare_ligand: Path
    prepare_gpf: Path
    autogrid4: Path
    ad4_parameters: Path
    autodock_gpu: Path
    fld_cutoff_line: int
    
    def __post_init__(self):
        """Valida existência das ferramentas na inicialização."""
        missing = []
        for field_name, value in self.__dict__.items():
            if field_name != 'fld_cutoff_line' and isinstance(value, Path):
                if not value.exists():
                    missing.append(field_name)
        
        if missing:
            raise RuntimeError(f"Ferramentas ausentes: {', '.join(missing)}")
    
    @classmethod
    @lru_cache(maxsize=1)
    def get_instance(cls) -> 'ToolPaths':
        """Singleton com cache para evitar recriação."""
        return cls(
            pythonsh=Path(os.getenv("PYTHONSH_PATH", 
                "/home/autodockgpu/mgltools_x86_64Linux2_1.5.7/bin/pythonsh")),
            prepare_receptor=Path(os.getenv("PREPARE_RECEPTOR4_PATH",
                "/home/autodockgpu/mgltools_x86_64Linux2_1.5.7/MGLToolsPckgs/AutoDockTools/Utilities24/prepare_receptor4.py")),
            prepare_ligand=Path(os.getenv("PREPARE_LIGAND4_PATH",
                "/home/autodockgpu/mgltools_x86_64Linux2_1.5.7/MGLToolsPckgs/AutoDockTools/Utilities24/prepare_ligand4.py")),
            prepare_gpf=Path(os.getenv("PREPARE_GPF4_PATH",
                "/home/autodockgpu/mgltools_x86_64Linux2_1.5.7/MGLToolsPckgs/AutoDockTools/Utilities24/prepare_gpf4.py")),
            autogrid4=Path(os.getenv("AUTOGRID4_BIN",
                "/home/autodockgpu/x86_64Linux2/autogrid4")),
            ad4_parameters=Path(os.getenv("AD4_PARAMETERS_DAT",
                "/home/autodockgpu/x86_64Linux2/AD4_parameters.dat")),
            autodock_gpu=Path(os.getenv("AUTODOCK_GPU_BIN",
                "/home/autodockgpu/AutoDock-GPU/bin/autodock_gpu_128wi")),
            fld_cutoff_line=int(os.getenv("FLD_APPEND_CUTOFF_LINE", "23"))
        )

# ====== Constantes otimizadas ======
LIGAND_GROUPS: Tuple[str, ...] = (
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
)

# ====== Classes para melhor organização ======
@dataclass
class GridParams:
    """Parâmetros de grid para cálculos."""
    size: Tuple[int, int, int]
    center: Tuple[float, float, float]
    
    @classmethod
    def from_strings(cls, size_str: Optional[str], center_str: Optional[str]) -> Optional['GridParams']:
        """Factory method para criar GridParams a partir de strings."""
        size = cls._parse_triplet_int(size_str) if size_str else None
        center = cls._parse_triplet_float(center_str) if center_str else None
        
        if size and center:
            return cls(size=size, center=center)
        return None
    
    @staticmethod
    def _parse_triplet_int(s: str) -> Tuple[int, int, int]:
        """Converte string para tripla de inteiros."""
        parts = [p for p in s.replace(",", " ").split() if p]
        if len(parts) != 3:
            raise ValueError(f"Expected 3 integers, got: {s}")
        return tuple(map(int, parts))
    
    @staticmethod
    def _parse_triplet_float(s: str) -> Tuple[float, float, float]:
        """Converte string para tripla de floats."""
        parts = [p for p in s.replace(",", " ").split() if p]
        if len(parts) != 3:
            raise ValueError(f"Expected 3 floats, got: {s}")
        return tuple(map(float, parts))

@dataclass
class DockingResult:
    """Resultado do docking molecular."""
    best_rmsd: Optional[float] = None
    best_energy: Optional[float] = None
    xml_path: Optional[Path] = None
    success: bool = False

class ProcessExecutor:
    """Gerencia execução de processos externos com melhor tratamento de erros."""
    
    @staticmethod
    def run(cmd: List[str], workdir: Path, tag: str, timeout: int = 300) -> None:
        """Executa comando com timeout e logging melhorado."""
        cmd_str = " ".join(shlex.quote(c) for c in cmd)
        logger.info("[%s] Executing: %s (cwd=%s)", tag, cmd_str, workdir)
        
        try:
            proc = subprocess.run(
                cmd, 
                cwd=str(workdir), 
                text=True, 
                capture_output=True,
                timeout=timeout,
                check=True
            )
            
            if proc.stdout:
                logger.debug("[%s] stdout: %s", tag, proc.stdout.strip())
            if proc.stderr and proc.stderr.strip():
                logger.warning("[%s] stderr: %s", tag, proc.stderr.strip())
                
        except subprocess.TimeoutExpired:
            logger.error("[%s] Timeout after %ds", tag, timeout)
            raise RuntimeError(f"{tag} timeout after {timeout}s")
        except subprocess.CalledProcessError as e:
            logger.error("[%s] Failed with rc=%d: %s", tag, e.returncode, e.stderr)
            raise RuntimeError(f"{tag} failed (rc={e.returncode})")
    
    @staticmethod
    def run_capture(cmd: List[str], workdir: Path, tag: str, timeout: int = 300) -> str:
        """Executa comando e captura stdout."""
        cmd_str = " ".join(shlex.quote(c) for c in cmd)
        logger.info("[%s] Executing: %s", tag, cmd_str)
        
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(workdir),
                text=True,
                capture_output=True,
                timeout=timeout,
                check=True
            )
            return proc.stdout or ""
            
        except subprocess.TimeoutExpired:
            logger.error("[%s] Timeout after %ds", tag, timeout)
            raise RuntimeError(f"{tag} timeout after {timeout}s")
        except subprocess.CalledProcessError as e:
            logger.error("[%s] Failed with rc=%d", tag, e.returncode)
            raise RuntimeError(f"{tag} failed (rc={e.returncode})")

class MoleculeProcessor:
    """Processa preparação de moléculas."""
    
    def __init__(self, workdir: Path, tools: ToolPaths):
        self.workdir = workdir
        self.tools = tools
        self.executor = ProcessExecutor()
    
    def prepare_receptor(self, receptor_pdb: Path) -> Path:
        """Prepara receptor convertendo PDB para PDBQT."""
        if not receptor_pdb.exists():
            raise FileNotFoundError(f"Receptor PDB not found: {receptor_pdb}")
        
        receptor_name = receptor_pdb.stem
        receptor_pdbqt = self.workdir / f"{receptor_name}.pdbqt"
        
        self.executor.run(
            [str(self.tools.pythonsh), str(self.tools.prepare_receptor),
             "-r", receptor_pdb.name, "-o", receptor_pdbqt.name],
            self.workdir,
            f"prepare_receptor_{receptor_name}"
        )
        
        if not receptor_pdbqt.exists():
            raise RuntimeError(f"Failed to generate receptor PDBQT: {receptor_pdbqt}")
        
        return receptor_pdbqt
    
    def prepare_ligand(self, ligand_pdb: Path) -> Optional[Path]:
        """Prepara ligante convertendo PDB para PDBQT."""
        if not ligand_pdb or not ligand_pdb.exists():
            return None
        
        ligand_name = ligand_pdb.stem
        ligand_pdbqt = self.workdir / f"{ligand_name}.pdbqt"
        
        self.executor.run(
            [str(self.tools.pythonsh), str(self.tools.prepare_ligand),
             "-l", ligand_pdb.name, "-o", ligand_pdbqt.name],
            self.workdir,
            f"prepare_ligand_{ligand_name}"
        )
        
        if not ligand_pdbqt.exists():
            raise RuntimeError(f"Failed to generate ligand PDBQT: {ligand_pdbqt}")
        
        return ligand_pdbqt
    
    def calculate_ligand_center(self, ligand_path: Path) -> Optional[Tuple[float, float, float]]:
        """Calcula centro geométrico do ligante com processamento otimizado."""
        if not ligand_path.exists():
            return None
        
        try:
            coords = []
            with ligand_path.open("r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if line.startswith(("ATOM", "HETATM")) and len(line) >= 54:
                        try:
                            x = float(line[30:38].strip())
                            y = float(line[38:46].strip())
                            z = float(line[46:54].strip())
                            coords.append((x, y, z))
                        except ValueError:
                            continue
            
            if coords:
                n = len(coords)
                center = tuple(sum(coord[i] for coord in coords) / n for i in range(3))
                logger.info("Calculated center from %s: (%.2f, %.2f, %.2f)", 
                           ligand_path.name, *center)
                return center
            
            logger.warning("No valid coordinates found in %s", ligand_path.name)
            return None
            
        except Exception as e:
            logger.exception("Error calculating center from %s: %s", ligand_path, e)
            return None
    
    def prepare_gpf_files(self, receptor_pdbqt: Path, grid_params: GridParams) -> List[Path]:
        """Prepara arquivos GPF em paralelo para melhor performance."""
        gpf_files = []
        
        def prepare_single_gpf(index: int, ligand_types: str) -> Path:
            gpf_name = f"grid_{index}.gpf"
            
            self.executor.run(
                [str(self.tools.pythonsh), str(self.tools.prepare_gpf),
                 "-r", receptor_pdbqt.name, "-o", gpf_name,
                 "-p", f"gridcenter={grid_params.center[0]},{grid_params.center[1]},{grid_params.center[2]}",
                 "-p", f"npts={grid_params.size[0]},{grid_params.size[1]},{grid_params.size[2]}",
                 "-p", f"ligand_types={ligand_types}"],
                self.workdir,
                f"prepare_gpf_{index}"
            )
            
            gpf_path = self.workdir / gpf_name
            if not gpf_path.exists():
                raise RuntimeError(f"Failed to generate {gpf_name}")
            
            # Adiciona parameter_file
            self._prepend_parameter_file(gpf_path)
            return gpf_path
        
        # Processa GPFs sequencialmente (pode ser paralelizado se necessário)
        for i, ligand_types in enumerate(LIGAND_GROUPS, start=1):
            gpf_files.append(prepare_single_gpf(i, ligand_types))
        
        return gpf_files
    
    def _prepend_parameter_file(self, gpf_path: Path) -> None:
        """Adiciona linha de parameter_file ao início do GPF."""
        content = gpf_path.read_text(encoding="utf-8")
        new_content = f"parameter_file {self.tools.ad4_parameters}\n{content}"
        gpf_path.write_text(new_content, encoding="utf-8")
        logger.debug("Added parameter_file to %s", gpf_path.name)
    
    def run_autogrid(self, gpf_files: List[Path]) -> Path:
        """Executa autogrid4 para todos os GPFs."""
        for i, gpf in enumerate(gpf_files, start=1):
            self.executor.run(
                [str(self.tools.autogrid4), "-p", gpf.name, "-l", f"grid_{i}.glg"],
                self.workdir,
                f"autogrid_{i}"
            )
        
        # Encontra arquivo FLD gerado
        fld_candidates = list(self.workdir.glob("*.maps.fld"))
        if not fld_candidates:
            raise RuntimeError("No *.maps.fld file generated by autogrid4")
        
        return fld_candidates[0]
    
    def postprocess_fld(self, fld_path: Path, receptor_name: str) -> None:
        """Pós-processa arquivo FLD com template otimizado."""
        if not fld_path.exists():
            logger.error("FLD file not found: %s", fld_path)
            return
        
        # Lê arquivo e mantém apenas linhas necessárias
        with fld_path.open("r", encoding="utf-8") as f:
            lines = f.readlines()
        
        keep_lines = lines[:self.tools.fld_cutoff_line] if len(lines) >= self.tools.fld_cutoff_line else lines
        
        # Adiciona template
        template = textfld().replace("kakakakaka", receptor_name)
        
        with fld_path.open("w", encoding="utf-8") as f:
            f.writelines(keep_lines)
            f.write(template)
        
        logger.info("Postprocessed %s (kept %d lines + template)", 
                   fld_path.name, len(keep_lines))
    
    def run_docking(self, fld_path: Path, ligand_pdbqt: Path) -> DockingResult:
        """Executa AutoDock-GPU e processa resultados."""
        if not ligand_pdbqt or not ligand_pdbqt.exists():
            return DockingResult()
        
        try:
            stdout = self.executor.run_capture(
                [str(self.tools.autodock_gpu), "--ffile", fld_path.name, 
                 "--lfile", ligand_pdbqt.name],
                self.workdir,
                f"autodock_gpu_{ligand_pdbqt.stem}",
                timeout=600  # 10 minutos para docking
            )
            
            # Extrai XML do output
            xml_text = self._extract_xml_from_text(stdout)
            
            # Se não encontrou no stdout, procura arquivo XML
            if not xml_text:
                xml_files = sorted(self.workdir.glob("*.xml"))
                if xml_files:
                    xml_text = xml_files[-1].read_text(encoding="utf-8")
                    xml_path = xml_files[-1]
                else:
                    xml_path = None
            else:
                # Salva XML extraído
                xml_path = self.workdir / "docking_result.xml"
                xml_path.write_text(xml_text, encoding="utf-8")
            
            # Parse resultados
            result = DockingResult(xml_path=xml_path, success=True)
            
            if xml_text:
                best = self._parse_best_from_xml(xml_text)
                if best:
                    result.best_rmsd, result.best_energy = best
                    logger.info("Docking result: RMSD=%.3f, Energy=%.2f kcal/mol",
                               result.best_rmsd, result.best_energy)
            
            return result
            
        except Exception as e:
            logger.error("Docking failed: %s", e)
            return DockingResult()
    
    @staticmethod
    def _extract_xml_from_text(text: str) -> Optional[str]:
        """Extrai conteúdo XML do texto."""
        start = text.find("<?xml")
        end_tag = "</autodock_gpu>"
        end = text.rfind(end_tag)
        
        if start != -1 and end != -1:
            return text[start:end + len(end_tag)]
        return None
    
    @staticmethod
    def _parse_best_from_xml(xml_text: str) -> Optional[Tuple[float, float]]:
        """Parse XML para extrair melhor resultado."""
        try:
            root = ET.fromstring(xml_text)
            runs = root.findall(".//result/rmsd_table/run")
            
            if not runs:
                return None
            
            # Encontra melhor RMSD
            best_rmsd = float('inf')
            best_energy = None
            
            for run in runs:
                rmsd = float(run.attrib.get("reference_rmsd", "inf"))
                energy = float(run.attrib.get("binding_energy", "0"))
                
                if rmsd < best_rmsd:
                    best_rmsd = rmsd
                    best_energy = energy
            
            if best_rmsd < float('inf'):
                return (best_rmsd, best_energy)
            
            return None
            
        except (ET.ParseError, ValueError, KeyError) as e:
            logger.error("Failed to parse AutoDock-GPU XML: %s", e)
            return None

# ====== Task Principal Otimizada ======
@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def prepare_macromolecule(
    self,
    workdir: str,
    receptor_filename: str,
    gridsize: Optional[str] = None,
    gridcenter: Optional[str] = None,
    ligand_filename: Optional[str] = None,
    macromolecule_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Task principal para preparação de macromolécula.
    
    Args:
        workdir: Diretório de trabalho
        receptor_filename: Nome do arquivo PDB do receptor
        gridsize: Tamanho do grid (ex: "60 60 60")
        gridcenter: Centro do grid (ex: "15.5 20.3 10.2")
        ligand_filename: Nome do arquivo PDB do ligante (opcional)
        macromolecule_id: ID da macromolécula no banco (opcional)
    
    Returns:
        Dict com informações do processamento
    """
    try:
        # Inicialização
        wd = Path(workdir)
        wd.mkdir(parents=True, exist_ok=True)
        
        tools = ToolPaths.get_instance()
        processor = MoleculeProcessor(wd, tools)
        
        receptor_name = Path(receptor_filename).stem
        receptor_pdb = wd / receptor_filename
        
        logger.info("=== Starting macromolecule preparation ===")
        logger.info("Workdir: %s", wd)
        logger.info("Receptor: %s", receptor_filename)
        if ligand_filename:
            logger.info("Ligand: %s", ligand_filename)
        
        # 1. Prepara receptor
        receptor_pdbqt = processor.prepare_receptor(receptor_pdb)
        
        # 2. Determina parâmetros do grid
        grid_params = GridParams.from_strings(gridsize, gridcenter)
        
        # Se não tem centro definido, tenta calcular do ligante
        if not grid_params and ligand_filename:
            ligand_pdb = wd / ligand_filename
            if ligand_pdb.exists():
                center = processor.calculate_ligand_center(ligand_pdb)
                if center and gridsize:
                    size = GridParams._parse_triplet_int(gridsize)
                    grid_params = GridParams(size=size, center=center)
        
        if not grid_params:
            raise ValueError("Grid parameters (size and center) are required")
        
        # 3. Prepara arquivos GPF
        gpf_files = processor.prepare_gpf_files(receptor_pdbqt, grid_params)
        
        # 4. Executa autogrid
        fld_path = processor.run_autogrid(gpf_files)
        
        # 5. Pós-processa FLD
        processor.postprocess_fld(fld_path, receptor_name)
        
        # 6. Prepara ligante (se fornecido)
        ligand_pdbqt = None
        if ligand_filename:
            ligand_pdb = wd / ligand_filename
            ligand_pdbqt = processor.prepare_ligand(ligand_pdb)
        
        # 7. Executa docking (se ligante disponível)
        docking_result = DockingResult()
        if ligand_pdbqt:
            docking_result = processor.run_docking(fld_path, ligand_pdbqt)
        
        # 8. Atualiza banco de dados
        db_updated = False
        if macromolecule_id and docking_result.success:
            db_updated = _update_database(
                macromolecule_id,
                docking_result.best_rmsd,
                docking_result.best_energy,
                str(fld_path)
            )
        
        # 9. Prepara resposta
        result = {
            "ok": True,
            "workdir": str(wd),
            "receptor_pdb": receptor_pdb.name,
            "receptor_pdbqt": receptor_pdbqt.name,
            "fld": fld_path.name,
            "gpf_count": len(gpf_files),
            "ligand_pdb": ligand_filename,
            "ligand_pdbqt": ligand_pdbqt.name if ligand_pdbqt else None,
            "gridcenter": grid_params.center,
            "gridsize": grid_params.size,
            "docking_ran": docking_result.success,
            "docking_xml": str(docking_result.xml_path) if docking_result.xml_path else None,
            "best_reference_rmsd": docking_result.best_rmsd,
            "best_binding_energy": docking_result.best_energy,
            "db_updated": db_updated,
            "macromolecule_id": macromolecule_id,
        }
        
        logger.info("=== Macromolecule preparation completed successfully ===")
        return result
        
    except Exception as e:
        logger.error("Task failed: %s", e, exc_info=True)
        
        # Retry se não for erro de validação
        if not isinstance(e, (ValueError, FileNotFoundError)):
            raise self.retry(exc=e)
        
        raise

def _update_database(
    macromolecule_id: str,
    rmsd: Optional[float],
    energy: Optional[float],
    fld_path: str
) -> bool:
    """Atualiza dados da macromolécula no banco."""
    try:
        with transaction.atomic():
            obj = Macromolecule.objects.select_for_update().filter(
                id=macromolecule_id
            ).first()
            
            if not obj:
                logger.warning("Macromolecule %s not found in database", macromolecule_id)
                return False
            
            # Atualiza apenas campos com novos valores
            update_fields = []
            
            if rmsd is not None:
                obj.rmsd_redocking = f"{rmsd:.3f}"
                update_fields.append("rmsd_redocking")
            
            if energy is not None:
                obj.energia_original = f"{energy:.2f}"
                update_fields.append("energia_original")
            
            if fld_path:
                obj.pathFilefld = fld_path
                update_fields.append("pathFilefld")
            
            if update_fields:
                obj.save(update_fields=update_fields)
                logger.info("Updated macromolecule %s: %s", 
                           macromolecule_id, ", ".join(update_fields))
                return True
            
            return False
            
    except Exception as e:
        logger.error("Failed to update database: %s", e, exc_info=True)
        return False