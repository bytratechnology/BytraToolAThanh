# -*- coding: mbcs -*-
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
#Khong doi
Original = 2420
#Parameter
Length = 2500
D = 203
XC = 21.03
B = 76
L = 22
LT_factor = 0.1
Bhole_factor = 0.2
t = 1.5
Model_name = 'LT01D_LK02D_C20024_L2500mm_XC'
Model_E1 = 'LT01D_LK02D_C20024_L2500mm_XC_E1'
Model_E2 = 'LT01D_LK02D_C20024_L2500mm_XC_E2'
#Parameter
translate_distance = Length - Original
E = Length/1500.0
E2 = E * -1.0
E1 = E
mdb.Model(name=Model_name, objectToCopy=
    mdb.models['Original'])
mdb.models[Model_name].parts['C10015'].features['Shell extrude-1'].setValues(
    depth=Length)
mdb.models[Model_name].parts['C10015'].regenerate()
mdb.models[Model_name].ConstrainedSketch(name=
    '__edit__', objectToCopy=
    mdb.models[Model_name].parts['C10015'].features['Shell extrude-1'].sketch)
mdb.models[Model_name].parts['C10015'].projectReferencesOntoSketch(
    filter=COPLANAR_EDGES, sketch=
    mdb.models[Model_name].sketches['__edit__'], 
    upToFeature=
    mdb.models[Model_name].parts['C10015'].features['Shell extrude-1'])
mdb.models[Model_name].sketches['__edit__'].parameters['D'].setValues(
    expression=str(D))
mdb.models[Model_name].sketches['__edit__'].parameters['XC'].setValues(
    expression=str(XC))
mdb.models[Model_name].sketches['__edit__'].parameters['B'].setValues(
    expression=str(B))
mdb.models[Model_name].sketches['__edit__'].parameters['L'].setValues(
    expression=str(L))
mdb.models[Model_name].parts['C10015'].features['Shell extrude-1'].setValues(
    sketch=mdb.models[Model_name].sketches['__edit__'])
del mdb.models[Model_name].sketches['__edit__']
mdb.models[Model_name].parts['C10015'].regenerate()
mdb.models[Model_name].ConstrainedSketch(name=
    '__edit__', objectToCopy=
    mdb.models[Model_name].parts['C10015'].features['Partition face-9'].sketch)
mdb.models[Model_name].parts['C10015'].projectReferencesOntoSketch(
    filter=COPLANAR_EDGES, sketch=
    mdb.models[Model_name].sketches['__edit__'], 
    upToFeature=
    mdb.models[Model_name].parts['C10015'].features['Partition face-9'])
mdb.models[Model_name].sketches['__edit__'].parameters['Length'].setValues(
    expression=str(Length))
mdb.models[Model_name].sketches['__edit__'].parameters['Lhole'].setValues(
    expression=str(D))
mdb.models[Model_name].sketches['__edit__'].parameters['LT_factor'].setValues(
    expression=str(LT_factor))
mdb.models[Model_name].sketches['__edit__'].parameters['Bhole_factor'].setValues(
    expression=str(Bhole_factor))
mdb.models[Model_name].parts['C10015'].features['Partition face-9'].setValues(
    sketch=mdb.models[Model_name].sketches['__edit__'])
del mdb.models[Model_name].sketches['__edit__']
mdb.models[Model_name].parts['C10015'].regenerate()
mdb.models[Model_name].sections['Member'].setValues(
    idealization=NO_IDEALIZATION, integrationRule=SIMPSON, material=
    'Steel - Flat Parts', nodalThicknessField='', numIntPts=5, preIntegrate=OFF
    , thickness=t, thicknessField='', thicknessType=UNIFORM)
mdb.models[Model_name].sections['Member-corner'].setValues(
    idealization=NO_IDEALIZATION, integrationRule=SIMPSON, material=
    'Steel - Flat Parts', nodalThicknessField='', numIntPts=5, preIntegrate=OFF
    , thickness=t, thicknessField='', thicknessType=UNIFORM)
mdb.models[Model_name].rootAssembly.regenerate()
mdb.models[Model_name].rootAssembly.translate(
    instanceList=('Plate-2', ), vector=(0.0, 0.0, translate_distance))
mdb.models[Model_name].parts['C10015'].generateMesh()
mdb.models[Model_name].rootAssembly.regenerate()
mdb.Job(atTime=None, contactPrint=OFF, description='', echoPrint=OFF, 
    explicitPrecision=SINGLE, getMemoryFromAnalysis=True, historyPrint=OFF, 
    memory=90, memoryUnits=PERCENTAGE, model=Model_name
    , modelPrint=OFF, multiprocessingMode=DEFAULT, name=Model_name, 
    nodalOutputPrecision=SINGLE, numCpus=2, numDomains=2, numGPUs=0, 
    numThreadsPerMpiProcess=1, queue=None, resultsFormat=ODB, scratch='', type=
    ANALYSIS, userSubroutine='', waitHours=0, waitMinutes=0)
mdb.Model(name=Model_E1, objectToCopy=
    mdb.models[Model_name])
mdb.models[Model_E1].rootAssembly.translate(
    instanceList=('C10015', ), vector=(0.0, E1, 0.0))
mdb.Model(name=Model_E2, objectToCopy=
    mdb.models[Model_name])
mdb.models[Model_E2].rootAssembly.translate(
    instanceList=('C10015', ), vector=(0.0, E2, 0.0))
mdb.Job(atTime=None, contactPrint=OFF, description='', echoPrint=OFF, 
    explicitPrecision=SINGLE, getMemoryFromAnalysis=True, historyPrint=OFF, 
    memory=90, memoryUnits=PERCENTAGE, model=Model_E1
    , modelPrint=OFF, multiprocessingMode=DEFAULT, name=Model_E1, 
    nodalOutputPrecision=SINGLE, numCpus=2, numDomains=2, numGPUs=0, 
    numThreadsPerMpiProcess=1, queue=None, resultsFormat=ODB, scratch='', type=
    ANALYSIS, userSubroutine='', waitHours=0, waitMinutes=0)
mdb.Job(atTime=None, contactPrint=OFF, description='', echoPrint=OFF, 
    explicitPrecision=SINGLE, getMemoryFromAnalysis=True, historyPrint=OFF, 
    memory=90, memoryUnits=PERCENTAGE, model=Model_E2
    , modelPrint=OFF, multiprocessingMode=DEFAULT, name=Model_E2, 
    nodalOutputPrecision=SINGLE, numCpus=2, numDomains=2, numGPUs=0, 
    numThreadsPerMpiProcess=1, queue=None, resultsFormat=ODB, scratch='', type=
    ANALYSIS, userSubroutine='', waitHours=0, waitMinutes=0)
