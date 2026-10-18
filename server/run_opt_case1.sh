#!/bin/bash

# set lib cell view
AE_LIB="2026_EDA_case1"
AE_CELL="OPA"
AE_VIEW="schematic"
MDE_CELL="OPA_loopgain"
#MDE_VIEW="spe_state1"
MDE_VIEW="spe_state1_Corner"

# set input param file
INPUT_PARAM_FILE="case1_extractcdfVal_0.txt"

# set output path file
OUTPUT_PATH="./case1_results"
OUTPUT_FILE="output.log"

# optimization use DE
pythone optimization.py --ae_lib ${AE_LIB} --ae_cell ${AE_CELL} --ae_view ${AE_VIEW} --mde_cell ${MDE_CELL} --mde_view ${MDE_VIEW} --param_file ${INPUT_PARAM_FILE} --output_path ${OUTPUT_PATH} --output_file ${OUTPUT_FILE} --use_algorithm_de

# optimization use DE, set symmtry devices and dummy device to reduce params
# DUMMY_DEVICES="NM8,NM5,NM6,NM7,PM0,PM1,PM5,PM14,NM2,NM3,NM0,PM15,PM8,PM9,PM11,PM12"
# SYMMTRY_DEVICES="(NM479,NM481),(PM_VINP,PM_VINN),(NM483,NM486),(NM484,NM485),(PM624,PM625),(PM623,PM626),(PM628,PM630),(PM627,PM629),(NM487,NM488),(R198,R199),(C311,C312),(PM631,PM633),(NM489,NM490)"
# pythone optimization.py --ae_lib ${AE_LIB} --ae_cell ${AE_CELL} --ae_view ${AE_VIEW} --mde_cell ${MDE_CELL} --mde_view ${MDE_VIEW} --param_file ${INPUT_PARAM_FILE} --output_path ${OUTPUT_PATH} --output_file ${OUTPUT_FILE} --use_algorithm_de --symmetry_devices ${SYMMTRY_DEVICES} --dummy_devices ${DUMMY_DEVICES}
