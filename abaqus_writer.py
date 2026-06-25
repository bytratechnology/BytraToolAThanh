"""Sinh script Abaqus/CAE từ Original_Compression_StubColumn_Long.py và tham số GUI."""

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from file_io import write_text
from inputs import ProcessInputs
from abaqus_job_settings import JOB_MEMORY_PERCENT, JOB_NUM_DOMAINS, resolve_job_num_cpus

ORIGINAL_LENGTH = 2420
DEFAULT_LT_FACTOR = 0.1
DEFAULT_BHOLE_FACTOR = 0.2
DEFAULT_ORIGINAL_MODEL = "Original"
DEFAULT_PART_NAME = "C10015"
DEFAULT_SHELL_FEATURE = "Shell extrude-1"
DEFAULT_PARTITION_FEATURE = "Partition face-9"


@dataclass
class AbaqusCaeSettings:
    """Cấu hình model CAE (theo Original_Compression_StubColumn_Long.py)."""

    cae_source: Path
    original_model: str = DEFAULT_ORIGINAL_MODEL
    part_name: str = DEFAULT_PART_NAME
    shell_feature: str = DEFAULT_SHELL_FEATURE
    partition_feature: str = DEFAULT_PARTITION_FEATURE
    lt_factor: float = DEFAULT_LT_FACTOR
    bhole_factor: float = DEFAULT_BHOLE_FACTOR
    original_length: float = ORIGINAL_LENGTH
    model_name: str = ""
    model_e1: str = ""
    model_e2: str = ""
    num_cpus: int = field(default_factory=resolve_job_num_cpus)


def _python_path(path: Path) -> str:
    return str(path.resolve()).replace("\\", "/")


def derive_model_names(inp_stem: str) -> tuple[str, str, str]:
    """
  Từ tên file .inp suy ra Model_name, Model_E1, Model_E2.
  Ví dụ: LT01D_LK02D_C20019_L6000mm_XC_E2 → base=..._XC, E1/E2 suffix.
    """
    stem = inp_stem
    for suffix in ("_IMPERFECTION", "_E1", "_E2"):
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
            break

    if stem.endswith("_XC"):
        base = stem
    else:
        base = stem

    return base, f"{base}_E1", f"{base}_E2"


def build_compression_stub_script(
    settings: AbaqusCaeSettings,
    inputs: ProcessInputs,
    *,
    work_dir: Path,
) -> str:
    """Tạo script CAE theo logic Original_Compression_StubColumn_Long.py."""
    length = inputs.length_l
    model_name, model_e1, model_e2 = derive_model_names(
        settings.model_name or settings.cae_source.stem
    )
    if settings.model_name:
        model_name = settings.model_name
    if settings.model_e1:
        model_e1 = settings.model_e1
    if settings.model_e2:
        model_e2 = settings.model_e2

    translate_distance = length - settings.original_length
    imperfection = length / 1500.0
    e1 = imperfection
    e2 = imperfection * -1.0

    cae_path = _python_path(settings.cae_source)
    work_path = _python_path(work_dir)
    original = settings.original_model
    part = settings.part_name
    shell = settings.shell_feature
    partition = settings.partition_feature
    cpus = settings.num_cpus
    mem = JOB_MEMORY_PERCENT
    domains = JOB_NUM_DOMAINS

    return f"""# -*- coding: mbcs -*-
# Generated — theo Original_Compression_StubColumn_Long.py
from part import *
from material import *
from section import *
from assembly import *
from step import *
from interaction import *
from load import *
from mesh import *
from optimization import *
from job import *
from sketch import *
from visualization import *
from connectorBehavior import *
import os

os.chdir(r'{work_path}')
openMdb(pathName=r'{cae_path}')

Original = {settings.original_length:g}
Length = {length:g}
D = {inputs.d:g}
XC = {inputs.xc:g}
B = {inputs.b:g}
L = {inputs.l:g}
LT_factor = {settings.lt_factor:g}
Bhole_factor = {settings.bhole_factor:g}
t = {inputs.thickness:g}
Model_name = '{model_name}'
Model_E1 = '{model_e1}'
Model_E2 = '{model_e2}'
translate_distance = Length - Original
E = Length / 1500.0
E2 = E * -1.0
E1 = E

mdb.Model(name=Model_name, objectToCopy=mdb.models['{original}'])
mdb.models[Model_name].parts['{part}'].features['{shell}'].setValues(depth=Length)
mdb.models[Model_name].parts['{part}'].regenerate()
mdb.models[Model_name].ConstrainedSketch(
    name='__edit__',
    objectToCopy=mdb.models[Model_name].parts['{part}'].features['{shell}'].sketch,
)
mdb.models[Model_name].parts['{part}'].projectReferencesOntoSketch(
    filter=COPLANAR_EDGES,
    sketch=mdb.models[Model_name].sketches['__edit__'],
    upToFeature=mdb.models[Model_name].parts['{part}'].features['{shell}'],
)
mdb.models[Model_name].sketches['__edit__'].parameters['D'].setValues(expression=str(D))
mdb.models[Model_name].sketches['__edit__'].parameters['XC'].setValues(expression=str(XC))
mdb.models[Model_name].sketches['__edit__'].parameters['B'].setValues(expression=str(B))
mdb.models[Model_name].sketches['__edit__'].parameters['L'].setValues(expression=str(L))
mdb.models[Model_name].parts['{part}'].features['{shell}'].setValues(
    sketch=mdb.models[Model_name].sketches['__edit__'],
)
del mdb.models[Model_name].sketches['__edit__']
mdb.models[Model_name].parts['{part}'].regenerate()
mdb.models[Model_name].ConstrainedSketch(
    name='__edit__',
    objectToCopy=mdb.models[Model_name].parts['{part}'].features['{partition}'].sketch,
)
mdb.models[Model_name].parts['{part}'].projectReferencesOntoSketch(
    filter=COPLANAR_EDGES,
    sketch=mdb.models[Model_name].sketches['__edit__'],
    upToFeature=mdb.models[Model_name].parts['{part}'].features['{partition}'],
)
mdb.models[Model_name].sketches['__edit__'].parameters['Length'].setValues(expression=str(Length))
mdb.models[Model_name].sketches['__edit__'].parameters['Lhole'].setValues(expression=str(D))
mdb.models[Model_name].sketches['__edit__'].parameters['LT_factor'].setValues(expression=str(LT_factor))
mdb.models[Model_name].sketches['__edit__'].parameters['Bhole_factor'].setValues(expression=str(Bhole_factor))
mdb.models[Model_name].parts['{part}'].features['{partition}'].setValues(
    sketch=mdb.models[Model_name].sketches['__edit__'],
)
del mdb.models[Model_name].sketches['__edit__']
mdb.models[Model_name].parts['{part}'].regenerate()
mdb.models[Model_name].sections['Member'].setValues(
    idealization=NO_IDEALIZATION,
    integrationRule=SIMPSON,
    material='Steel - Flat Parts',
    nodalThicknessField='',
    numIntPts=5,
    preIntegrate=OFF,
    thickness=t,
    thicknessField='',
    thicknessType=UNIFORM,
)
mdb.models[Model_name].sections['Member-corner'].setValues(
    idealization=NO_IDEALIZATION,
    integrationRule=SIMPSON,
    material='Steel - Flat Parts',
    nodalThicknessField='',
    numIntPts=5,
    preIntegrate=OFF,
    thickness=t,
    thicknessField='',
    thicknessType=UNIFORM,
)
mdb.models[Model_name].rootAssembly.regenerate()
mdb.models[Model_name].rootAssembly.translate(
    instanceList=('Plate-2',),
    vector=(0.0, 0.0, translate_distance),
)
mdb.models[Model_name].parts['{part}'].generateMesh()
mdb.models[Model_name].rootAssembly.regenerate()
mdb.Job(
    atTime=None, contactPrint=OFF, description='', echoPrint=OFF,
    explicitPrecision=SINGLE, getMemoryFromAnalysis=True, historyPrint=OFF,
    memory={mem}, memoryUnits=PERCENTAGE, model=Model_name, modelPrint=OFF,
    multiprocessingMode=THREADS, name=Model_name, nodalOutputPrecision=SINGLE,
    numCpus={cpus}, numDomains={domains}, numGPUs=0, numThreadsPerMpiProcess=1,
    queue=None, resultsFormat=ODB, scratch='', type=ANALYSIS,
    userSubroutine='', waitHours=0, waitMinutes=0,
)
mdb.Model(name=Model_E1, objectToCopy=mdb.models[Model_name])
mdb.models[Model_E1].rootAssembly.translate(
    instanceList=('{part}',),
    vector=(0.0, E1, 0.0),
)
mdb.Model(name=Model_E2, objectToCopy=mdb.models[Model_name])
mdb.models[Model_E2].rootAssembly.translate(
    instanceList=('{part}',),
    vector=(0.0, E2, 0.0),
)
mdb.Job(
    atTime=None, contactPrint=OFF, description='', echoPrint=OFF,
    explicitPrecision=SINGLE, getMemoryFromAnalysis=True, historyPrint=OFF,
    memory={mem}, memoryUnits=PERCENTAGE, model=Model_E1, modelPrint=OFF,
    multiprocessingMode=THREADS, name=Model_E1, nodalOutputPrecision=SINGLE,
    numCpus={cpus}, numDomains={domains}, numGPUs=0, numThreadsPerMpiProcess=1,
    queue=None, resultsFormat=ODB, scratch='', type=ANALYSIS,
    userSubroutine='', waitHours=0, waitMinutes=0,
)
mdb.Job(
    atTime=None, contactPrint=OFF, description='', echoPrint=OFF,
    explicitPrecision=SINGLE, getMemoryFromAnalysis=True, historyPrint=OFF,
    memory={mem}, memoryUnits=PERCENTAGE, model=Model_E2, modelPrint=OFF,
    multiprocessingMode=THREADS, name=Model_E2, nodalOutputPrecision=SINGLE,
    numCpus={cpus}, numDomains={domains}, numGPUs=0, numThreadsPerMpiProcess=1,
    queue=None, resultsFormat=ODB, scratch='', type=ANALYSIS,
    userSubroutine='', waitHours=0, waitMinutes=0,
)
"""


def write_compression_stub_script(
    settings: AbaqusCaeSettings,
    inputs: ProcessInputs,
    *,
    work_dir: Path,
    script_output: Path,
) -> Path:
    content = build_compression_stub_script(settings, inputs, work_dir=work_dir)
    write_text(
        script_output,
        content,
        encoding="mbcs" if sys.platform == "win32" else "utf-8",
    )
    return script_output


def parse_inp_variant(inp_stem: str) -> str | None:
    """Trả về 'E1' hoặc 'E2' nếu tên file .inp có hậu tố tương ứng."""
    match = re.search(r"_E([12])(?:_IMPERFECTION)?$", inp_stem, re.IGNORECASE)
    if match:
        return f"E{match.group(1)}"
    return None
