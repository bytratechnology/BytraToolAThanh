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
mdb.models['LT00D_LK01D_C10015_L2p5_Original'].parts['C10015'].features['Shell extrude-1'].setValues(
    depth=4000.001)
mdb.models['LT00D_LK01D_C10015_L2p5_Original'].parts['C10015'].regenerate()
mdb.models['LT00D_LK01D_C10015_L2p5_Original'].ConstrainedSketch(name=
    '__edit__', objectToCopy=
    mdb.models['LT00D_LK01D_C10015_L2p5_Original'].parts['C10015'].features['Shell extrude-1'].sketch)
mdb.models['LT00D_LK01D_C10015_L2p5_Original'].parts['C10015'].projectReferencesOntoSketch(
    filter=COPLANAR_EDGES, sketch=
    mdb.models['LT00D_LK01D_C10015_L2p5_Original'].sketches['__edit__'], 
    upToFeature=
    mdb.models['LT00D_LK01D_C10015_L2p5_Original'].parts['C10015'].features['Shell extrude-1'])
mdb.models['LT00D_LK01D_C10015_L2p5_Original'].sketches['__edit__'].parameters['D'].setValues(
    expression='203.001')
mdb.models['LT00D_LK01D_C10015_L2p5_Original'].sketches['__edit__'].parameters['XC'].setValues(
    expression='21.001')
mdb.models['LT00D_LK01D_C10015_L2p5_Original'].sketches['__edit__'].parameters['B'].setValues(
    expression='76.001')
mdb.models['LT00D_LK01D_C10015_L2p5_Original'].sketches['__edit__'].parameters['L'].setValues(
    expression='20.001')
mdb.models['LT00D_LK01D_C10015_L2p5_Original'].parts['C10015'].features['Shell extrude-1'].setValues(
    sketch=mdb.models['LT00D_LK01D_C10015_L2p5_Original'].sketches['__edit__'])
del mdb.models['LT00D_LK01D_C10015_L2p5_Original'].sketches['__edit__']
mdb.models['LT00D_LK01D_C10015_L2p5_Original'].parts['C10015'].regenerate()
mdb.models['LT00D_LK01D_C10015_L2p5_Original'].ConstrainedSketch(name=
    '__edit__', objectToCopy=
    mdb.models['LT00D_LK01D_C10015_L2p5_Original'].parts['C10015'].features['Partition face-9'].sketch)
mdb.models['LT00D_LK01D_C10015_L2p5_Original'].parts['C10015'].projectReferencesOntoSketch(
    filter=COPLANAR_EDGES, sketch=
    mdb.models['LT00D_LK01D_C10015_L2p5_Original'].sketches['__edit__'], 
    upToFeature=
    mdb.models['LT00D_LK01D_C10015_L2p5_Original'].parts['C10015'].features['Partition face-9'])
mdb.models['LT00D_LK01D_C10015_L2p5_Original'].sketches['__edit__'].parameters['Length'].setValues(
    expression='4000.001')
mdb.models['LT00D_LK01D_C10015_L2p5_Original'].sketches['__edit__'].parameters['Lhole'].setValues(
    expression='203.001')
mdb.models['LT00D_LK01D_C10015_L2p5_Original'].parts['C10015'].features['Partition face-9'].setValues(
    sketch=mdb.models['LT00D_LK01D_C10015_L2p5_Original'].sketches['__edit__'])
del mdb.models['LT00D_LK01D_C10015_L2p5_Original'].sketches['__edit__']
mdb.models['LT00D_LK01D_C10015_L2p5_Original'].parts['C10015'].regenerate()
mdb.models['LT00D_LK01D_C10015_L2p5_Original'].parts['C10015'].generateMesh()
mdb.models['LT00D_LK01D_C10015_L2p5_Original'].rootAssembly.regenerate()
mdb.Job(atTime=None, contactPrint=OFF, description='', echoPrint=OFF, 
    explicitPrecision=SINGLE, getMemoryFromAnalysis=True, historyPrint=OFF, 
    memory=90, memoryUnits=PERCENTAGE, model='LT00D_LK01D_C10015_L2p5_Original'
    , modelPrint=OFF, multiprocessingMode=DEFAULT, name=
    'LT00D_LK02D_C20019_L4p0_Original', nodalOutputPrecision=SINGLE, numCpus=2, 
    numDomains=2, numGPUs=0, numThreadsPerMpiProcess=1, queue=None, 
    resultsFormat=ODB, scratch='', type=ANALYSIS, userSubroutine='', waitHours=
    0, waitMinutes=0)
mdb.models['LT00D_LK01D_C10015_L2p5_Original'].sections['Member'].setValues(
    idealization=NO_IDEALIZATION, integrationRule=SIMPSON, material=
    'Steel - Flat Parts', nodalThicknessField='', numIntPts=5, preIntegrate=OFF
    , thickness=1.9, thicknessField='', thicknessType=UNIFORM)
