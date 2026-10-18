import pyAether as ae
import argparse
import re
import os
import shutil
import numpy as np
from typing import Dict, Optional, List, Tuple, Set, Union
from scipy.optimize import differential_evolution


def merge_files(file_list, output_file):
    """Merge multiple files into a single output file"""
    with open(output_file, 'w') as output:
        for file_name in file_list:
            with open(file_name, 'r') as input_file:
                output.write(input_file.read())
                output.write("\n\n")


def extract_params(lib, cell, view, param_file_name):
    cv = ae.dbOpenCV(lib, cell, view)
    if(cv is None):
        print("dbOpenCV failed !!!")
        return

    with open(param_file_name, 'w') as param_file:
        insts = cv.instances
        for inst in insts:
            # print("=====start ", inst.name, "=====")
            if (inst.name[0] == "R"  or  inst.name[0] == 'r'):
                retVal = ae.aeEmyInstGetParameter('segW', inst)
                strlog = f"parameter, {inst.name}_segW, {retVal}\n"
                param_file.write(strlog)

                retVal = ae.aeEmyInstGetParameter('segL', inst)
                strlog = f"parameter, {inst.name}_segL, {retVal}\n"
                param_file.write(strlog)

            elif (inst.name[0] == "C"  or  inst.name[0] == 'c'):
                retVal = ae.aeEmyInstGetParameter('l', inst)
                strlog = f"parameter, {inst.name}_l, {retVal}\n"
                param_file.write(strlog)

            elif (str(inst.name).startswith("PM")  or  str(inst.name).startswith("NM")):
                retVal = ae.aeEmyInstGetParameter('m', inst)
                strlog = f"parameter, {inst.name}_m, {retVal}\n"
                param_file.write(strlog)

                retVal = ae.aeEmyInstGetParameter('l', inst)
                strlog = f"parameter, {inst.name}_l, {retVal}\n"
                param_file.write(strlog)

                retVal = ae.aeEmyInstGetParameter('fw', inst)
                strlog = f"parameter, {inst.name}_fw, {retVal}\n"
                param_file.write(strlog)

            else:
                # print(f"==== Instance {inst.name} no params need extract.")
                continue

            # print("=====finish ", inst.name, "=====")
    ae.dbCloseCV(cv)


def param_convert(s: str) -> float:
    """
    Convert a string with unit to micrometers (\u03bcm).
    Supported units: 
        'u' or '\u03bcm' for micrometers (default unit)
        'n' or 'nm' for nanometers
        No unit indicates meters
    Supports scientific notation (e.g., '1.5e-3u') and sign prefixes
    
    Parameters:
        s (str): Input string with optional unit
    Returns:
        float: Value converted to micrometers
    Raises:
        ValueError: For unrecognized units or invalid number formats
    """
    # Regular expression pattern to match optional sign, number (with scientific notation), and optional unit
    pattern = r'^\s*([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)\s*([a-zA-Z]*)\s*$'
    match = re.match(pattern, s)
    
    # Handle cases where input doesn't match expected pattern
    if not match:
        raise ValueError(f"Unparseable input format: '{s}'")
    
    # Extract number and unit components from matched groups
    number_str, unit = match.groups()
    
    try:
        # Convert number string to float (supports scientific notation)
        value = float(number_str)
    except ValueError:
        raise ValueError(f"Invalid number format: '{number_str}'")
    
    # Normalize unit string: lowercase and replace micro symbol (\u03bc) with 'u'
    unit = unit.lower().replace('\u03bc', 'u').replace('m', '')
    
    # Convert value based on detected unit
    if unit == '' or unit == 'u':  # No unit (meters) or micrometers
        return value if unit == 'u' else value * 1e6
    elif unit == 'n':  # Nanometers
        return value * 0.001
    else:
        raise ValueError(f"Unrecognized unit: '{unit}'. Supported units: 'u' (micrometers), 'n' (nanometers), or no unit (meters)")


class Parameter:
    """Represents an optimization parameter with constraints"""
    def __init__(
        self,
        name: str,
        param_type: str = 'continuous',
        value: float = None,
        min_val: float = None,
        max_val: float = None,
        is_dummy: bool = False
    ):
        self.name = name
        self.type = param_type
        self.value = value
        self.min = min_val
        self.max = max_val
        self.is_dummy = is_dummy

    def format_value(self, value: float) -> str:
        """Format value according to parameter type and unit"""
        if self.type == 'integer':
            return str(int(round(value)))
        else:
            if (value < 1.0):
                return f"{value * 1000}n"
            else:
                return f"{value}u"

    def format(self) -> str:
        """Format value according to parameter type and unit"""
        if self.type == 'integer':
            return str(int(round(self.value)))
        else:
            if (self.value < 1.0):
                return f"{self.value * 1000}n"
            else:
                return f"{self.value}u"

    def normalize(self, value: float) -> float:
        """Normalize a value to [0, 1] range based on parameter bounds"""
        if self.max == self.min:
            return 0.0  # Avoid division by zero
        return (value - self.min) / (self.max - self.min)

    def denormalize(self, norm_value: float) -> float:
        """Convert a normalized value back to the original range"""
        return self.min + norm_value * (self.max - self.min)


class SymmetryConstraint:
    """Represents a symmetry constraint between instances"""
    def __init__(self, instance_groups: List[Union[Tuple[str, ...], List[str]]]):
        self.instance_groups = instance_groups
        self.symmetric_groups = self._create_symmetric_groups()
        
    def _create_symmetric_groups(self) -> List[Set[str]]:
        """Create symmetric groups from instance groups"""
        groups = []
        for group in self.instance_groups:
            # Convert tuple to set
            group_set = set(group)
            # Check if any instance already exists in existing groups
            merged_groups = []
            new_group = group_set.copy()
            
            for existing_group in groups:
                if existing_group & group_set:
                    # Merge with existing group
                    new_group |= existing_group
                else:
                    # Keep existing group as is
                    merged_groups.append(existing_group)
            
            merged_groups.append(new_group)
            groups = merged_groups
        
        return groups

    def get_symmetric_parameters_for_group(self, group: Set[str], param_name: str) -> List[str]:
        """Get all symmetric parameter names for a given parameter in a specific group"""
        symmetric_params = []
        for inst in group:
            symmetric_params.append(f"{inst}_{param_name}")
        return symmetric_params

    def get_symmetric_groups_for_instance(self, instance_name: str) -> Set[str]:
        """Get the symmetric group for a specific instance"""
        for group in self.symmetric_groups:
            if instance_name in group:
                return group
        return {instance_name}  # Return singleton if not in any group


def apply_symmetry_constraints(parameters: Dict[str, Parameter], symmetry_constraints: SymmetryConstraint) -> Tuple[Dict[str, Parameter], Dict[str, List[str]]]:
    """Apply symmetry constraints to parameters and reduce parameter count"""
    # Create a mapping from original parameter names to merged parameter names
    param_mapping = {}
    reduced_parameters = {}
    
    # First process parameters in symmetry groups
    for group in symmetry_constraints.symmetric_groups:
        # Create a representative parameter for each parameter type
        for param_type in ['m', 'l', 'fw', 'segW', 'segL']:
            symmetric_params = symmetry_constraints.get_symmetric_parameters_for_group(group, param_type)
            
            # Check if these parameters exist in the original parameters
            existing_params = [p for p in symmetric_params if p in parameters]
            if not existing_params:
                continue
                
            # Select the first parameter as the representative parameter
            representative_param = existing_params[0]
            rep_param_obj = parameters[representative_param]
            
            # Create merged parameter
            # Use the name of the first instance in the group and the parameter type as the new parameter name
            first_instance = next(iter(group))
            merged_param_name = f"{first_instance}_{param_type}"
            
            # Create merged parameter object
            merged_param = Parameter(
                merged_param_name,
                rep_param_obj.type,
                rep_param_obj.value,
                rep_param_obj.min,
                rep_param_obj.max
            )
            
            # Add to reduced parameters list
            reduced_parameters[merged_param_name] = merged_param
            
            # Record mapping relationship
            for param_name in existing_params:
                param_mapping[param_name] = merged_param_name
    
    # Add non-symmetric parameters
    for param_name, param in parameters.items():
        if param_name not in param_mapping:
            # This parameter does not belong to any symmetry group, add directly to the reduced parameters list
            reduced_parameters[param_name] = param
            param_mapping[param_name] = param_name
    
    print(f"Parameter count reduced from {len(parameters)} to {len(reduced_parameters)}")
    
    return reduced_parameters, param_mapping


def read_parameters(file_name, dummy_devices: List[str] = None) -> Dict[str, Parameter]:
    """Read parameters from a configuration file"""
    parameters = {}
    if dummy_devices is None:
        dummy_devices = []

    with open(file_name, 'r') as param_file:
        lines = param_file.readlines()
        for line in lines:
            fields = line.strip().replace('"', '').replace(" ", "").split(',')
            if fields[0] == "parameter":
                name = fields[1]
                index = name.rfind("_")
                inst_name = fields[1][:index]
                param_name = name[(index+1):]

                # Check if this is a dummy device
                is_dummy = inst_name in dummy_devices
            
                if param_name == "m":
                    min_val = 1
                    max_val = 20
                    param_value = float(fields[2])
                    if (int(round(param_value)) < min_val) or (int(round(param_value)) > max_val):
                        RuntimeError(f'The param {param_name} of instance {inst_name} is out of range [{min_val}, {max_val}]!!!')
                    param = Parameter(name, 'integer', param_value, min_val, max_val, is_dummy)
                else:
                    min_val = 0.13
                    max_val = 20.0
                    param_value = param_convert(fields[2])
                    if (param_value < min_val) or (param_value > max_val):
                        RuntimeError(f'The param {param_name} of instance {inst_name} is out of range [{min_val}, {max_val}]!!!')
                    param = Parameter(name, 'continuous', param_value, min_val, max_val, is_dummy)
                parameters[name] = param
        print(f'==== Read {len(parameters)} parameters successfully, param file: {file_name} ====\n')
    return parameters


class SimulatePlatform:
    """Platform for circuit optimization using Aether tools"""
    def __init__(
        self,
        ae_lib: str = None,
        ae_cell: str = None,
        ae_view: str = None,
        mde_cell: str = None,
        mde_view: str = None,
        output_path: str = None,
        output_file: str = None,
        best_param_file: str = None,
        symmetry_constraints: Optional[SymmetryConstraint] = None,
        dummy_params: Dict[str, Parameter] = None
    ):
        self.origin_lib = ae_lib
        self.ae_lib = ae_lib
        self.ae_cell = ae_cell
        self.ae_view = ae_view
        self.mde_cell = mde_cell
        self.mde_view = mde_view
        self.output_path = output_path
        self.output_file = output_file
        self.best_param_file = best_param_file
        self.symmetry_constraints = symmetry_constraints
        self.dummy_params = dummy_params or {}
        self.best_fitness = 1e10
        self.best_iter = 0
        self.best_path = ''
        self.iter_count = 0  # Track iterations
        self.param_mapping = {}  # original param ---> reduced param
        self.reverse_mapping = {}  # Reverse mapping from reduced to original parameters
        self.base_ugb = 0.0
        self.base_area = 0.0
        self.base_gain = 0.0

        if os.path.exists(self.output_path):
            shutil.rmtree(self.output_path)
            print(f"delete old dir: {self.output_path}")
    
        os.makedirs(self.output_path, exist_ok=True)
        print(f"create new dir: {self.output_path}")


    def set_params(self, reduced_params: Dict[str, Parameter], values: np.ndarray):
        """Apply parameter values to the circuit design"""
        cv = ae.dbOpenCV(self.ae_lib, self.ae_cell, self.ae_view)
        if not cv:
            raise RuntimeError(f'ae.dbOpenCV({self.ae_lib}, {self.ae_cell}, {self.ae_view}) failed')

        # Map reduced parameter values back to original parameters
        reduced_param_items = list(reduced_params.items())

        # Apply parameter values
        for i, (reduced_name, param) in enumerate(reduced_param_items):
            # Get all original parameters corresponding to this reduced parameter
            original_params = self.reverse_mapping.get(reduced_name, [reduced_name])
            for orig_name in original_params:
                # Parse instance name and parameter name
                index = orig_name.rfind("_")
                inst_name = orig_name[:index]
                param_name = orig_name[(index+1):]

                instId = ae.dbFindInst(cv=cv, name=inst_name)
                if not instId:
                    print(f'Warning: Instance {inst_name} not found')
                    continue

                formatted_value = param.format_value(values[i])
                # print(f"Set {inst_name} {param_name} = {formatted_value}")

                # Set params
                ret = ae.cdfSetParam(instId, param_name, formatted_value)
                if not ret:
                    print(f'Warning: Set {orig_name}={formatted_value} failed')

        # Set dummy parameters to their minimum values
        for dummy_name, dummy_param in self.dummy_params.items():
            # Parse instance name and parameter name
            index = dummy_name.rfind("_")
            inst_name = dummy_name[:index]
            param_name = dummy_name[(index+1):]
            
            instId = ae.dbFindInst(cv=cv, name=inst_name)
            if not instId:
                print(f'Warning: Dummy instance {inst_name} not found')
                continue
            
            # Set dummy parameter to minimum value
            formatted_value = dummy_param.format_value(dummy_param.min)
            ret = ae.cdfSetParam(instId, param_name, formatted_value)
            if not ret:
                print(f'Warning: Set dummy {dummy_name}={formatted_value} failed')
            # else:
            #     print(f'Set dummy {dummy_name} to minimum value: {formatted_value}')

        save_result = ae.dbCheckAndSaveDesign(cv)
        print(f'Design save result: {save_result}')
        ae.dbCloseCV(cv)

    def only_set_params(self, params: Dict[str, Parameter]):
        """Apply parameter values to the circuit design"""
        cv = ae.dbOpenCV(self.ae_lib, self.ae_cell, self.ae_view)
        if not cv:
            raise RuntimeError(f'ae.dbOpenCV({self.ae_lib}, {self.ae_cell}, {self.ae_view}) failed')

        param_items = list(params.items())
        # Apply parameter values
        for i, (orig_name, param) in enumerate(param_items):
            # Parse instance name and parameter name
            index = orig_name.rfind("_")
            inst_name = orig_name[:index]
            param_name = orig_name[(index + 1):]

            instId = ae.dbFindInst(cv=cv, name=inst_name)
            if not instId:
                print(f'Warning: Instance {inst_name} not found')
                continue

            formatted_value = param.format_value(param.value)
            # print(f"Set {inst_name} {param_name} = {formatted_value}")

            # Set params
            ret = ae.cdfSetParam(instId, param_name, formatted_value)
            if not ret:
                print(f'Warning: Set {orig_name}={formatted_value} failed')

        save_result = ae.dbCheckAndSaveDesign(cv)
        print(f'Design save result: {save_result}')
        ae.dbCloseCV(cv)


    def normalize_values(self, reduced_params: Dict[str, Parameter], real_values: np.ndarray) -> np.ndarray:
        """Normalize real parameter values to [0, 1] range"""
        normalized_values = np.zeros_like(real_values)
        reduced_param_items = list(reduced_params.items())
        
        for i, (name, param) in enumerate(reduced_param_items):
            normalized_values[i] = param.normalize(real_values[i])
            
        return normalized_values


    def denormalize_values(self, reduced_params: Dict[str, Parameter], normalized_values: np.ndarray) -> np.ndarray:
        """Convert normalized parameter values back to real range"""
        real_values = np.zeros_like(normalized_values)
        reduced_param_items = list(reduced_params.items())
        
        for i, (name, param) in enumerate(reduced_param_items):
            real_values[i] = param.denormalize(normalized_values[i])
            
        return real_values


    def calc_area(self):
        """Compute total area of the chip"""
        cv = ae.dbOpenCV(self.ae_lib, self.ae_cell, self.ae_view)
        if not cv:
            raise RuntimeError(f'ae.dbOpenCV({self.ae_lib}, {self.ae_cell}, {self.ae_view}) failed, please check !!!')

        insts = cv.instances
        self.total_area = 0.0
        for inst in insts:
            if (inst.name[0] == "R"  or  inst.name[0] == 'r'):
                # segW * segL * segments * 2.0
                segW = str(ae.aeEmyInstGetParameter('segW', inst))
                segL = str(ae.aeEmyInstGetParameter('segL', inst))
                segments = str(ae.aeEmyInstGetParameter('segments', inst))
                r_area = param_convert(segW) * param_convert(segL) * float(segments) * 2.0
                # print(f'======== {inst.name} area:  {segW} * {segL} * {segments} * 2.0 = {r_area}')
                self.total_area += r_area

            elif (inst.name[0] == "C"  or  inst.name[0] == 'c'):
                # fw * l* m * 1.0
                fw = str(ae.aeEmyInstGetParameter('fw', inst))
                l = str(ae.aeEmyInstGetParameter('l', inst))
                m = str(ae.aeEmyInstGetParameter('m', inst))
                c_area = param_convert(fw) * param_convert(l) * float(m)
                # print(f'======== {inst.name} area:  {fw} * {l} * {m} * 1.0 = {c_area}')
                self.total_area += c_area

            elif (str(inst.name).startswith("PM")  or  str(inst.name).startswith("NM")):
                # fw * l * m * 1.5
                fw = str(ae.aeEmyInstGetParameter('fw', inst))
                l = str(ae.aeEmyInstGetParameter('l', inst))
                m = str(ae.aeEmyInstGetParameter('m', inst))
                m_area = param_convert(fw) * param_convert(l) * float(m) * 1.5
                # print(f'======== {inst.name} area:  {fw} * {l} * {m} * 1.5 = {m_area}')
                self.total_area += m_area

            else:
                continue
                # print(f'======== {inst.name} area:  not counted!!! ==========================')
        print(f'\n==== total area:  {self.total_area}')
        ae.dbCloseCV(cv)


    def evaluate(self) -> Dict[str, float]:
        """Run simulation and collect results"""

        # Create unique output directory for this evaluation
        self.iter_count += 1
        eval_path = f"{self.output_path}/iter_{self.iter_count}"

        # compute area
        self.calc_area()

        # open mde
        mde = ae.MdeSession.open(self.ae_lib, self.mde_cell, self.mde_view)
        if mde:
            print(f"\n==== iter {self.iter_count} ae.MdeSession.open({self.ae_lib}, {self.mde_cell}, {self.mde_view}) successfully ====")
        else:
            print(f"\n==== iter {self.iter_count} ae.MdeSession.open({self.ae_lib}, {self.mde_cell}, {self.mde_view}) failed. Reason: {ae.MdeSession.staticLastError()}")
            return ""

        print(f'\n==== iter {self.iter_count} Project directory: {mde.getSetting().getProjectDirectory()}')
        setting = mde.getSetting()
        print(f'\n==== iter {self.iter_count} Current settings: {setting}')
        # print(f'\n==== SPE outputs: {setting.getAllSpeOutputs()}')
	
        if (mde.createSimulationNetlist()):
            print("Creating simulation netlist succeeds.")
        else:
            print("Creating simulation netlist fails.")
 
        # Execute simulation
        scores = {}
        print(f"\n==== iter {self.iter_count} Begin simulate ====")
        result = mde.netlistAndRun()
        if result:
            print(f"\n==== iter {self.iter_count} Simulation completed successfully ====")
        else:
            print(f'\n==== iter {self.iter_count} Simulation failed. Reason: {mde.lastError()}')
            mde.close()
            return scores
	    
        if not result.isValid():
            print(f'\n==== iter {self.iter_count} Invalid results. Reason: {result.lastError()}')
            mde.close()
            return scores
	    
        # Save results in CSV format
        result.saveResultsToDir(eval_path)
        if not result.isValid():
            print(f'\n==== iter {self.iter_count} Results are invalid. Reason: {result.lastError()}')
            mde.close()
            return scores
        

        # Copy simulation log file
        src_path = f"{mde.getSetting().getProjectDirectory()}/{self.ae_lib}/{self.mde_cell}/{self.mde_view}/Results/{result.name()[len('Results'):]}"
        try:
            shutil.copy2(f"{src_path}/emy2netlist.log", f"{eval_path}/emy2netlist.log")
        except Exception as e:
            print(f"Failed to copy emy2netlist.log, details: {str(e)}")
    
        if mde.close():
            print(f"==== iter {self.iter_count} Succeeds in closing MDE ====")
        else:
            print(f"==== iter {self.iter_count} Fails to close MDE, reason: {mde.lastError()}")

        # Combine results into single log file
        print(f'\n==== iter {self.iter_count} Result name: {result.name()}')
        merge_files([f"{eval_path}/{result.name()}_summary.csv"], f"{eval_path}/{self.output_file}")

        # Save simulation result
        with open(f"{eval_path}/{self.output_file}", 'r') as csvfile:
            with open(f"{eval_path}/result.txt", 'w') as f:
                import csv
                reader = csv.DictReader(csvfile)
                for row in reader:
                    if (row['Output'] == "Phase_Margin") or (row['Output'] == "Gain_db") or (row['Output'] == "UGB"):
                        strlog = f"{row['Output']} {row['Min']}\n"
                        f.write(strlog)
                        if row['Min'] == '':
                            scores[row['Output']] = -float("inf")
                        else:
                            scores[row['Output']] = float(row['Min'])
                    elif (row['Output'] == "Gain_Margin") or (row['Output'] == "I_OPA"):
                        strlog = f"{row['Output']} {row['Max']}\n"
                        f.write(strlog)
                        if row['Max'] == '':
                            scores[row['Output']] = float("inf")
                        else:
                            scores[row['Output']] = float(row['Max'])
                    else:
                        continue

                # save total area
                strlog = f"Total_Area {self.total_area}\n"
                scores['Total_Area'] = self.total_area
                f.write(strlog)

        # Save params
        extract_params(self.ae_lib, self.ae_cell, self.ae_view, f"{eval_path}/params.txt")
        print(f"\n========== Evaluation result of iter {self.iter_count} ==========")
        print(f"====== UGB          : {scores['UGB']} Hz")
        print(f"====== Phase_Margin : {scores['Phase_Margin']} deg")
        print(f"====== Gain_db      : {scores['Gain_db']} db")
        print(f"====== Gain_Margin  : {scores['Gain_Margin']} deg")
        print(f"====== I_OPA        : {scores['I_OPA'] * 1000.0} mA")
        print(f"====== Total_Area   : {scores['Total_Area']} um^2\n")
        return scores


    def optimization_objective(self, normalized_values: np.ndarray, 
                            reduced_params: Dict[str, Parameter]) -> float:
        """Objective function for optimization"""

        real_values = self.denormalize_values(reduced_params, normalized_values)

        # Run simulation and get performance score
        self.set_params(reduced_params, real_values)  # set params
        scores = self.evaluate()

        # Compute fitness
        fitness = 0.0
        phase_margin = scores['Phase_Margin']
        if (phase_margin == -float("inf")):
            fitness += 1e9
        elif (phase_margin < 0.1):
            fitness += 1e7
        elif (phase_margin < 50.0):      # constraint PM >= 50
            fitness += (1e6 * (50.0 - phase_margin) / 50.0 + 1e6)   # 1e6 ~ 2e6

        gain_margin = scores['Gain_Margin']
        if (gain_margin == float("inf")):
            fitness += 1e9
        elif (gain_margin > -0.1):
            fitness += 1e7
        elif (gain_margin > -10.0):      # constraint GM <= -10
            fitness += (1e6 * (10.0 + gain_margin) / 10.0 + 1e6)    # 1e6 ~ 2e6

        gain_db = scores['Gain_db']
        if (gain_db == -float("inf")):
            fitness += 1e9
        elif (gain_db < 20.0):           # hard constraint: Gain must be > 20 db
            fitness += 1e9
        else:
            # Gain is an optimization objective: the larger the better,
            # normalized by the first feasible gain value (same style as UGB)
            if (self.base_gain < 1.0):
                self.base_gain = gain_db
            fitness -= (gain_db / self.base_gain * 100.0)

        if (scores['I_OPA'] == float("inf")):
            fitness += 1e9
        elif (scores['I_OPA'] > 0.003):  # constraint I_OPA <= 3 mA
            fitness += 1e6

        # Expected UGB to be large
        if (scores['UGB'] == -float("inf")):
            fitness += 1e9
        else:
            ugb = scores['UGB']
            if (self.base_ugb < 1.0):
                self.base_ugb = ugb
            fitness -= (ugb / self.base_ugb * 150.0)

        # Expected small area
        area = scores['Total_Area']
        if (self.base_area < 1.0):
            self.base_area = area
        fitness += (area / self.base_area * 150.0)

        print(f"==== iter {self.iter_count} fitness: {fitness}")

        # Track best fitness
        if (fitness < self.best_fitness):
            self.best_fitness = fitness
            self.best_iter = self.iter_count
            self.best_path = f"{self.output_path}/iter_{self.iter_count}"
            print(f"New best score: {fitness}")

            extract_params(self.ae_lib, self.ae_cell, self.ae_view, f"{self.best_param_file}")

            with open(f"{self.output_path}/best_result.txt", 'w') as best_f:
                best_f.write(f"Best iter    : {self.best_iter}\n")
                best_f.write(f"Best path    : {self.best_path}\n")
                best_f.write(f"UGB          : {scores['UGB']} Hz\n")
                best_f.write(f"Phase_Margin : {scores['Phase_Margin']} deg\n")
                best_f.write(f"Gain_db      : {scores['Gain_db']} db\n")
                best_f.write(f"Gain_Margin  : {scores['Gain_Margin']} deg\n")
                best_f.write(f"I_OPA        : {scores['I_OPA'] * 1000.0} mA\n")
                best_f.write(f"Total_Area   : {scores['Total_Area']} um^2\n")
                best_f.write(f"Fitness      : {fitness}\n")

        return fitness


    def create_initial_population(
        self,
        reduced_params: Dict[str, Parameter],
        pop_size: int,
        perturb_ratio: float = 0.05
    ) -> np.ndarray:
        """Create initial population near the initial parameter point.

        The first individual is exactly the initial point (from the param file),
        remaining individuals are perturbed around it with a Gaussian
        perturbation (std = perturb_ratio) in normalized [0,1] space.
        """
        param_items = list(reduced_params.items())
        init_point = np.array([param.normalize(param.value) for _, param in param_items])
        # population size must be > 4 for differential_evolution
        pop_size = max(pop_size, 5)
        pop = np.tile(init_point, (pop_size, 1))
        pop += np.random.normal(0.0, perturb_ratio, size=(pop_size, len(param_items)))
        pop = np.clip(pop, 0.0, 1.0)
        pop[0] = init_point  # keep the exact initial point as the first individual
        return pop

    def run_de_optimization(
        self,
        reduced_params: Dict[str, Parameter],
        max_iter: int = 10,
        pop_size: int = 5
    ):
        """Run differential evolution optimization"""
        print("\n==== Starting Differential Evolution Optimization ====")

        # Prepare parameter bounds for DE (normalized to [0,1])
        param_items = list(reduced_params.items())
        bounds = [(0, 1)] * len(param_items)

        # Initialize population near the initial point so that DE first
        # explores the neighborhood of the design provided in the param file
        init_population = self.create_initial_population(reduced_params, pop_size * len(param_items))
        print(f"Initial population size: {init_population.shape[0]} (initialized around the initial design point)")

        try:
            print("\n==== Optimization Begin ====")
            print(f"pop_size: {pop_size}, max_iter: {max_iter}, params_num: {len(param_items)}")
            # Run differential evolution
            result = differential_evolution(
                func=lambda x: self.optimization_objective(x, reduced_params),
                bounds=bounds,
                init=init_population,
                maxiter=max_iter,
                tol=0.01,
                mutation=(0.5, 1.0),
                recombination=0.7,
                strategy='best1bin',
                polish=False,
                workers=1
            )

            # Print optimization results
            print("\n==== Optimization Completed ====")
            print(f"Success: {result.success}")
            print(f"Message: {result.message}")
            print(f"Final cost: {result.fun}")
            print("Optimized parameters:")

            # Convert normalized results to actual values
            real_values = self.denormalize_values(reduced_params, result.x)
            for i, (name, param) in enumerate(param_items):
                print(f"  {name}: {param.format_value(real_values[i])}")

            # Save best parameters to file
            with open(f"{self.output_path}/optimized_params.txt", 'w') as f:
                f.write("Optimized Parameters:\n")
                for i, (name, param) in enumerate(param_items):
                    f.write(f"{name}: {param.format_value(real_values[i])}\n")
                f.write(f"\nFinal Performance: {result.fun}")

        except Exception as e:
            # Handle user interruption
            print(f"\n\n=== Optimization interrupted by user ===\n{e}")
            print(f"Best solution found at iteration {self.best_iter}")
            print(f"Best parameters saved to: {self.best_path}")


def parse_symmetry_constraints(constraint_str: str) -> SymmetryConstraint:
    """Parse symmetry constraints from string format"""
    if not constraint_str or constraint_str.strip() == "":
        return None
        
    groups = []
    # Parse format like: "(PM1,PM2,PM3),(NM4,NM5),(NM6,NM7,NM8,NM9)"
    pattern = r'\(([^)]+)\)'
    matches = re.findall(pattern, constraint_str)
    
    for match in matches:
        instances = [inst.strip() for inst in match.split(',')]
        if len(instances) > 1:  # Only add groups with at least 2 instances
            groups.append(tuple(instances))
    
    return SymmetryConstraint(groups)


def parse_arguments():
    """Parse command-line arguments for the optimization tool"""
    parser = argparse.ArgumentParser(
        description='Circuit Optimization Platform',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument('--ae_lib', required=True, help='Aether library name')
    parser.add_argument('--ae_cell', required=True, help='Aether cell name')
    parser.add_argument('--ae_view', required=True, help='Aether view name')
    parser.add_argument('--mde_cell', required=True, help='MDE cell name')
    parser.add_argument('--mde_view', required=True, help='MDE view name')
    parser.add_argument('--param_file', required=True, help='Parameter file name')
    parser.add_argument('--best_param_file', required=True, help='Out best parameter file name')

    # Option Parameters
    parser.add_argument('--output_path', default='./results', help='Output directory path')
    parser.add_argument('--output_file', default='output.log', help='Output file name')
    parser.add_argument('--symmetry_devices', default='', 
                        help='Symmetry devices in format "(inst1,inst2,inst3),(inst4,inst5)"')
    parser.add_argument('--dummy_devices', default='', 
                        help='Dummy devices in format "inst1,inst2,inst3"')

    # Optimization parameters
    parser.add_argument('--max_iter', type=int, default=100,
                        help='Maximum number of iterations')
    parser.add_argument('--pop_size', type=int, default=300,
                        help='Population size for differential evolution')
    parser.add_argument('--verbose', action='store_true',
                        help='Enable verbose output for debugging')
    parser.add_argument('--set_params', action='store_true',
                        help='Set parameters using specific param_file')
    parser.add_argument('--evaluate', action='store_true',
                        help='Simulate using specific parameters')
    parser.add_argument('--use_algorithm_de', action='store_true',
                        help='Using the DE algorithm to optimize parameters')

    return parser.parse_args()


# =====================================================================
# [PATCH-MODULE3] 模块三改进：默认约减 + 预算感知 + 目标函数对齐真实评分
# 生成脚本：module3/tools/make_submission.py（依据 run_score.sh / score.py 实测）
# =====================================================================
import types
import time

TIME_LIMIT_TOTAL = 10800.0      # run_score.sh 默认 3 小时
BUDGET_RATIO = float(os.environ.get('OPT_BUDGET_RATIO', '0.80'))   # 留 20% 收尾/落盘/异常
MIN_POP = 12
MAX_POP = 36
MAX_ITER_CAP = 200
RANDOM_SEED = int(os.environ.get('OPT_SEED', '2026'))

# [P0-10] 初值局部化（v1 的归一化 sigma 保留作对照，实际使用 P0-13 的相对扰动）
LOCAL_SIGMA = float(os.environ.get('OPT_LOCAL_SIGMA', '0.08'))

# [P0-13] 种群规模固定，maxiter 交给硬截止控制，不再用不可靠的 t_eval 反推
POP_FIXED = int(os.environ.get('OPT_POP', '20'))
REL_SIGMA = float(os.environ.get('OPT_REL_SIGMA', '0.50'))   # 每个参数按自身值 ±50%
SPARSE_P = float(os.environ.get('OPT_SPARSE_P', '0.35'))     # 每个候选只动 35% 的参数

# [P0-11] 面积预剪枝：先只算面积（CV 读一遍，很便宜），面积超过初始解的 N 倍就
# 跳过整次 PVT 仿真。面积是 25 分的大头，离谱点不可能赢，省下的时间给有效点。
AREA_CAP_FACTOR = float(os.environ.get('OPT_AREA_CAP_FACTOR', '6.0'))

# 服务器上冒烟测试用：OPT_TIME_LIMIT=300 就只跑 5 分钟（判分时不设这个变量 -> 10800）
TIME_LIMIT_TOTAL = float(os.environ.get('OPT_TIME_LIMIT', str(TIME_LIMIT_TOTAL)))

# score.py 的真实基线（run_score.sh 传入）
SCORE_GAIN_MIN_DB = 20.0

# [P0-14] 增益项的基准，默认 20dB（= score.py 原样，保证自动分最优）。
# 若想把增益往 40dB 推（赛题 6.3(3) 的最终排名门槛），用 OPT_GAIN_TARGET=40 启动。
# 代价：会拿 Area 的分去换增益（Area 在 score.py 里值 25 分，增益超 20dB 后是 0 分）。
SCORE_GAIN_TARGET_DB = float(os.environ.get('OPT_GAIN_TARGET', '20.0'))

# =====================================================================
# [P0-15] 按赛题 6.3 的真实评分表重写目标函数（默认启用）
#   约束 30 分：PM>=50 (10) / GM<=-10dB (10) / I_OPA<=3mA (10)
#   目标 40 分：DC Gain>=40dB 才计分，40~60dB 线性 (10)
#               UGB 越大越好 (15)     Area 越小越好 (15)
#   时间 10 分：单次运行内无法横向比较，按满分；每违反一条约束扣 5
#   合计 80 分（对应 6.3 里模块三的部分）
# 说明：6.3 的 UGB/Gain/Area 真实得分是"与其他队伍比值"，赛场上无从得知，
#       这里用参考值做线性归一（可用环境变量调整，便于按往届水平校准）。
# =====================================================================
# [P0-16] 增益硬门槛：DC Gain < 40dB 的候选一律不选（用户明确要求）。
# 实跑证据：局部 ±15% 扰动只能把增益停在 25~31dB，永远够不到 40dB。
# 所以同时做两件事：
#   ① fitness 里给 <40dB 加 1e5 级惩罚，并按"离 40 还有多远"排序（够不到 40 时至少往 40 靠）
#   ② 扰动改成增益导向：只放大 l / fw（抬高 ro 与 gm），其余参数仍双向扰动
GAIN_GATE = os.environ.get('OPT_GAIN_GATE', '1') == '1'
GAIN_GATE_PENALTY = 1.0e5
UP_ONLY_SUFFIX = ('l', 'fw')   # [P0-18] 撤掉 m：实测 m 增大会抬高面积却换不到 UGB

# [P0-17] 电流窗口：目标 2.5~2.8mA（用预算换 UGB），worst-case 不超 2.8mA。
# 理由：score.py 取 PVT 最坏值判 I_OPA<=3mA，留 0.2mA 余量才稳；
#       而 UGB 15 分是大头，提电流是最直接的手段。
IOPA_SCORE_MAX_A = float(os.environ.get('OPT_IOPA_MAX', '0.003'))   # 6.3 硬约束
IOPA_SOFT_HI_A = float(os.environ.get('OPT_IOPA_HI', '0.0028'))     # 内部软上限
IOPA_TARGET_LO_A = float(os.environ.get('OPT_IOPA_LO', '0.0025'))   # 期望下限

PM_MIN_DEG = float(os.environ.get('OPT_PM_MIN', '50.0'))
GM_MAX_DB = float(os.environ.get('OPT_GM_MAX', '-10.0'))
IOPA_MAX_A = float(os.environ.get('OPT_IOPA_MAX', '0.003'))   # 3mA；电流想放宽就调大

# [P0-19] 目标转向 UGB + Area：
#   Gain 门槛 43 -> 41（用户要求），且 GAIN_REF 也设成 41：
#   一旦过门槛就吃满增益那 10 分，不再奖励"多推 2dB"——把算力全让给 UGB 与 Area。
#   UGB 参考 50MHz -> 12MHz、Area 参考 8000 -> 9000：
#   这两个是"策略参考值"（6.3 真实得分是与其他队伍比值，赛场上未知），
#   目的是让搜索在可达区间内仍有明显梯度，而不是一律贴近 0。
GAIN_MIN_DB = float(os.environ.get('OPT_GAIN_MIN', '41.0'))
GAIN_REF_DB = float(os.environ.get('OPT_GAIN_REF', '41.0'))
UGB_REF_HZ = float(os.environ.get('OPT_UGB_REF', '1.2e7'))    # 12MHz 视为满分
AREA_REF_UM2 = float(os.environ.get('OPT_AREA_REF', '9000.0'))


def _est_score_pdf(scores):
    """赛题 6.3 口径的 80 分制评分（模块三部分）。"""
    s = 0.0
    viol = 0.0
    n_bad = 0
    pm = scores.get('Phase_Margin')
    gm = scores.get('Gain_Margin')
    gain = scores.get('Gain_db')
    iopa = scores.get('I_OPA')
    ugb = scores.get('UGB')
    area = scores.get('Total_Area')

    # ---- 约束 30 分 ----
    if pm is None or pm == -float('inf'):
        viol += 6.0
        n_bad += 1
    elif pm >= PM_MIN_DEG:
        s += 10.0
    else:
        viol += 1.0 + (PM_MIN_DEG - pm) / 5.0
        n_bad += 1

    if gm is None or gm == float('inf'):
        viol += 6.0
        n_bad += 1
    elif gm <= GM_MAX_DB:
        s += 10.0
    else:
        viol += 1.0 + (gm - GM_MAX_DB) / 2.0
        n_bad += 1

    if iopa is None or iopa == float('inf'):
        viol += 6.0
        n_bad += 1
    elif iopa <= IOPA_SCORE_MAX_A:
        s += 10.0
        # [P0-18] 撤掉"+3 电流奖励"：实测 37 次评估里没有一个点进入 2.5~2.8mA，
        # 加了奖励后达标点反而从 3 个掉到 1 个、最高增益从 45.3 掉到 41.0。
        # 只保留 2.8mA 软上限做 PVT 安全余量。
        if iopa > IOPA_SOFT_HI_A:
            viol += (iopa - IOPA_SOFT_HI_A) / 2.0e-4
    else:
        viol += 1.0 + (iopa - IOPA_SCORE_MAX_A) / 0.001
        n_bad += 1

    # ---- 目标 40 分 ----
    # Gain：>=40dB 才计分（6.3(3)），40~GAIN_REF 线性到 10 分
    if gain is None or gain == -float('inf'):
        viol += 6.0
        n_bad += 1
    elif gain >= GAIN_MIN_DB:
        s += min(gain / GAIN_REF_DB, 1.0) * 10.0
    else:
        # 未到 40dB：该项记 0 分，但留 0~3 分的过渡梯度把它往上拉
        s += max(gain, 0.0) / GAIN_MIN_DB * 3.0

    # UGB：越大越好
    if ugb is not None and ugb > 1.0:
        s += min(ugb / UGB_REF_HZ, 1.0) * 15.0

    # Area：越小越好
    if area is not None and area > 1.0:
        s += min(AREA_REF_UM2 / area, 1.0) * 15.0

    # ---- 时间 10 分 ----
    s += max(0.0, 10.0 - 5.0 * n_bad)
    return s, viol
SCORE_UGB_BASE = 2.0e8
SCORE_AREA_BASE = 8000.0

# ---- P0-2：时间预算的真实口径 ----
# run_score.sh 的 TIME_LIMIT=10800s 只是"杀进程"上限；
# 而 score.py 的时间分满分区是 execution_time <= time_base = 7200s。
# 也就是说跑满 8640s 会让时间分从 20 掉到 7200/8640*20 ≈ 16.7，白丢 3.3 分。
# 所以优化预算必须夹到 7200 - 余量 以内。
TIME_FULL_SCORE = 7200.0
TIME_SAFETY = 300.0

# 模块二识别结果（针对本赛题电路；Hidden 电路名字不同会被自动过滤掉）
DEFAULT_DUMMY_DEVICES = "R5,R6,C4,C5"
DEFAULT_SYMMETRY_DEVICES = (
    "(NM15,NM14),(PM11,PM7),(PM10,PM9),(PM3,PM2),(NM4,NM5),(NM6,NM7),"
    "(NM8,NM9),(NM10,NM11),(NM12,NM13),(PM8,PM12),(R1,R2),(R0,R3),(C0,C11),(C2,C3)"
)


# =====================================================================
# [P0-3] 参数上下界：严格对齐 score.py 的 read_parameters()
# 上游模板对"所有连续参数"一律用 0.13..20，但 score.py 实际按参数名分别 clamp：
#   m / segments : 整数 1..100
#   l            : 电容(C*) 4..30，其余 0.13..20
#   fw           : 0.15..50
#   segW         : 0.42..10
#   segL         : 5..100
# 不一致的后果：优化器在 [0,1] 归一化空间里探索的点，反归一化后落在评分时会被
# clamp 掉的区间 -> "优化出来的解" ≠ "最终被评的解"，白花仿真次数。
# =====================================================================
_BOUNDS = {
    'm':        (1.0, 100.0, 'integer'),
    'segments': (1.0, 100.0, 'integer'),
    'fw':       (0.15, 50.0, 'continuous'),
    'segW':     (0.42, 10.0, 'continuous'),
    'segL':     (5.0, 100.0, 'continuous'),
    'l':        (0.13, 20.0, 'continuous'),
}
_CAP_L = (4.0, 30.0)


def _bounds_for(inst_name, param_name):
    """返回 (min, max, type)，口径同 score.py。"""
    if param_name == 'l' and inst_name[:1] in ('C', 'c'):
        return _CAP_L[0], _CAP_L[1], 'continuous'
    return _BOUNDS.get(param_name, (0.13, 20.0, 'continuous'))


def _patched_read_parameters(file_name, dummy_devices=None):
    """替代上游 read_parameters：同样的单位换算、同样的上下界、同样的 clamp 策略。

    上游用 0.13..20 一把尺子量所有连续参数，与 score.py 的 clamp 区间不一致；
    这里逐参数对齐，保证"优化空间 == 评分空间"。
    """
    parameters = {}
    dummy_devices = dummy_devices or []
    with open(file_name, 'r') as param_file:
        for line in param_file:
            fields = line.strip().replace('"', '').replace(' ', '').split(',')
            if len(fields) < 3 or fields[0] != 'parameter':
                continue
            name = fields[1]
            index = name.rfind('_')
            inst_name = name[:index]
            param_name = name[(index + 1):]
            lo, hi, ptype = _bounds_for(inst_name, param_name)
            try:
                if ptype == 'integer':
                    value = float(fields[2])
                else:
                    value = param_convert(fields[2])
            except Exception as e:
                print('WARN: 跳过无法解析的参数行 %r (%s)' % (line.strip(), e), flush=True)
                continue
            # score.py 的做法是 clamp（不报错），这里保持一致
            if value < lo:
                value = lo
            if value > hi:
                value = hi
            parameters[name] = Parameter(name, ptype, value, lo, hi,
                                         inst_name in dummy_devices)
    # 记住输入文件的变量清单（原样、原序），供 [P0-4] 回写时严格复用
    global INPUT_SCHEMA
    INPUT_SCHEMA = list(parameters.keys())
    print('==== [P0-3] Read %d parameters (bounds aligned with score.py): %s ===='
          % (len(parameters), file_name), flush=True)
    return parameters


# [P0-4 修订] 回写必须"照抄输入参数文件的 schema"，不能自己发明变量。
# 实测 case1_params_0.txt 的组成（105=29*3+6*1+6*2）：
#   MOS (29 个) : fw, l, m       -> 87
#   电容 (6 个) : l 只有 1 个     -> 6
#   电阻 (6 个) : segL, segW      -> 12
# 也就是说电容**没有** fw/m、电阻**没有** segments。
# （score.py::calc_area 里的 fw/m/segments 是它直接从电路 CV 读的，与参数文件无关。）
# 上游 extract_params 的硬编码 schema 恰好与之一致，所以这里改为：
#   - 默认：按输入文件里实际出现过的变量名逐个回写（严格同名同序）；
#   - OPT_EXTRA_PARAMS=1 时才追加 R_segments / C_fw / C_m 做实验。
INPUT_SCHEMA = []


def _patched_extract_params(lib, cell, view, param_file_name):
    """[P0-4] 按输入参数文件的 schema 回写最优解。

    为什么不再自己拼 if/elif：
      回写文件是交给 score.py::read_parameters 再 set 回电路的，
      多写一个输入文件里没有的参数，就等于偷偷改了赛方的参数化口径。
    """
    cv = ae.dbOpenCV(lib, cell, view)
    if cv is None:
        print('dbOpenCV failed !!!', flush=True)
        return
    extra = os.environ.get('OPT_EXTRA_PARAMS', '0') == '1'

    with open(param_file_name, 'w') as param_file:
        if INPUT_SCHEMA:
            # 主路径：严格复用输入文件的变量清单
            for name in INPUT_SCHEMA:
                idx = name.rfind('_')
                inst_name, param_name = name[:idx], name[idx + 1:]
                inst = ae.dbFindInst(cv=cv, name=inst_name)
                if not inst:
                    continue
                try:
                    val = ae.aeEmyInstGetParameter(param_name, inst)
                except Exception:
                    continue
                if val is None:
                    continue
                param_file.write('parameter, %s, %s\n' % (name, val))
            if extra:
                for inst in cv.instances:
                    n = str(inst.name)
                    more = ()
                    if n[:1] in ('R', 'r'):
                        more = ('segments',)
                    elif n[:1] in ('C', 'c'):
                        more = ('fw', 'm')
                    for k in more:
                        try:
                            val = ae.aeEmyInstGetParameter(k, inst)
                        except Exception:
                            continue
                        if val is not None:
                            param_file.write('parameter, %s_%s, %s\n' % (n, k, val))
        else:
            # 兜底：没读到输入文件时，退回上游的同款 schema
            for inst in cv.instances:
                n = str(inst.name)
                if n[:1] in ('R', 'r'):
                    keys = ('segW', 'segL')
                elif n[:1] in ('C', 'c'):
                    keys = ('l',)
                elif n.startswith('PM') or n.startswith('NM'):
                    keys = ('fw', 'l', 'm')
                else:
                    continue
                for k in keys:
                    try:
                        val = ae.aeEmyInstGetParameter(k, inst)
                    except Exception:
                        continue
                    if val is not None:
                        param_file.write('parameter, %s_%s, %s\n' % (n, k, val))
    ae.dbCloseCV(cv)
    print('==== [P0-4] wrote %d lines (schema=%s) -> %s ===='
          % (len(INPUT_SCHEMA) if INPUT_SCHEMA else -1,
             'from input file' if INPUT_SCHEMA else 'fallback', param_file_name), flush=True)


# 覆盖上游同名全局函数：_patched_objective / _patched_run_de 里用的是全局名，故会自动生效
_UPSTREAM_READ_PARAMETERS = read_parameters
_UPSTREAM_EXTRACT_PARAMS = extract_params
read_parameters = _patched_read_parameters
extract_params = _patched_extract_params


def _fix_sim_paths():
    """[P0-8] 修复 MDE 配置里指向旧机器的绝对路径 —— 这是"全员 0 分"的真正根因。

    实跑证据（server/2026_EDA_case1_optimization.log L46-50）：
        Creating simulation netlist fails.
        Simulation failed. Reason: "File does not exist:
        /home/eda_2025/EDA_2025_Empyrean_lab_start/hes_release/models/spectre/spe_demo.scs."

    而工作目录下 ./hes_release/models/spectre/spe_demo.scs 是**存在**的
    （run_score.sh 会 cp -rf circuits/* 到工作目录，circuits 里带 hes_release）。

    做法（不硬编码任何用户名/年份，纯按"存在性"判断）：
      扫描 MDE 的 setting / adeL2View.file / *.scs，
      把其中**不存在**的绝对路径里 `hes_release/` 之后的部分，
      重定向到 <当前工作目录>/hes_release/...（只有当那个位置确实存在时才改）。
    """
    root = os.getcwd()
    pat = re.compile(r'/[^\s"\'<>,;:]*hes_release/[^\s"\'<>,;:]*')
    targets = []
    for dirpath, dirnames, files in os.walk('.'):
        # 跳过体积大又无关的目录，保证启动时间
        dirnames[:] = [d for d in dirnames
                       if d not in ('hes_release', 'layout', '__pycache__')]
        for fn in files:
            if fn in ('setting', 'adeL2View.file') or fn.endswith('.scs'):
                targets.append(os.path.join(dirpath, fn))
        if len(targets) > 500:
            break

    def _repl(m):
        old = m.group(0)
        if os.path.exists(old):
            return old                      # 本来就能访问，不动
        tail = old.split('/hes_release/', 1)[1]
        cand = os.path.join(root, 'hes_release', tail)
        return cand if os.path.exists(cand) else old

    fixed = 0
    for p in targets:
        try:
            with open(p, 'r', errors='ignore') as f:
                txt = f.read()
        except Exception:
            continue
        new = pat.sub(_repl, txt)
        if new != txt:
            try:
                with open(p, 'w') as f:
                    f.write(new)
                fixed += 1
                print('[P0-8] 修复模型路径: %s' % p, flush=True)
            except Exception as e:
                print('[P0-8] 写入失败 %s: %s' % (p, e), flush=True)
    print('==== [P0-8] 模型路径修复完成：扫描 %d 个候选文件，改动 %d 个（cwd=%s）===='
          % (len(targets), fixed, root), flush=True)


def _inst_names_of(parameters):
    """从参数名（形如 NM2_fw）反推实例名集合。"""
    return {n.rsplit('_', 1)[0] for n in parameters}


def _filter_groups(parameters, dummy_str, sym_str):
    """把默认分组过滤成"该电路里真实存在"的器件，避免 Hidden 电路报错。"""
    names = _inst_names_of(parameters)
    dummies = [d.strip() for d in dummy_str.split(',') if d.strip() and d.strip() in names]
    groups = []
    for g in re.findall(r'\(([^)]*)\)', sym_str):
        insts = [x.strip() for x in g.split(',') if x.strip()]
        insts = [x for x in insts if x in names]
        if len(insts) >= 2:
            groups.append(insts)
    return ','.join(dummies), ','.join('(%s)' % ','.join(g) for g in groups)


def _est_score(scores):
    """按 score.py 的真实公式估算得分（满分 100，不含时间分/时间罚分）。

    返回 (score, viol)：viol 是"归一化后的约束违反量"，用来在不可行时提供梯度。
    """
    s = 0.0
    viol = 0.0
    pm = scores.get('Phase_Margin')
    gm = scores.get('Gain_Margin')
    gain = scores.get('Gain_db')
    iopa = scores.get('I_OPA')
    ugb = scores.get('UGB')
    area = scores.get('Total_Area')

    if pm is None or pm == -float('inf'):
        viol += 6.0
    elif pm >= 50.0:
        s += 10.0
    else:
        viol += 1.0 + (50.0 - pm) / 5.0

    if gm is None or gm == float('inf'):
        viol += 6.0
    elif gm <= -10.0:
        s += 10.0
    else:
        viol += 1.0 + (10.0 + gm) / 2.0

    # 注意边界：score.py 是 `if gain_db < 20.0` 才算违反 -> gain == 20 可行且满分
    if gain is not None and gain >= SCORE_GAIN_MIN_DB:
        s += min(gain / SCORE_GAIN_TARGET_DB, 1.0) * 10.0
    else:
        viol += 6.0

    if iopa is not None and iopa <= 0.003:
        s += 10.0
    else:
        viol += 6.0

    if ugb is not None and ugb > 1.0:
        s += min(ugb / SCORE_UGB_BASE, 1.0) * 15.0
    if area is not None and area > 1.0:
        s += min(SCORE_AREA_BASE / area, 1.0) * 25.0
    return s, viol


def _patched_objective(self, normalized_values, reduced_params):
    """可行性优先：不可行时 fitness 由 viol 主导；可行后等价于最大化真实评分。"""
    real_values = self.denormalize_values(reduced_params, normalized_values)
    self.set_params(reduced_params, real_values)

    # [P0-12] 硬截止：预算用完后的评估立即返回（不再跑仿真）。
    # 实跑证据：OPT_TIME_LIMIT=300 -> 预算 240s，实际跑了 1043.8s（超 4.3 倍）。
    # 原因是 scipy 的 callback 每代只调一次，maxiter=1 时等于没检查。
    # 正式跑若照样超时，会被 run_score.sh 在 10800s 强杀 -> 时间分掉到 13.3 且可能写不出 best。
    if getattr(self, '_deadline', None) is not None and time.time() > self._deadline:
        self.iter_count = getattr(self, 'iter_count', 0) + 1
        print('==== iter %d TIMEOUT-SKIP（预算已用完，跳过仿真）====' % self.iter_count,
              flush=True)
        return 1e9

    # [P0-11] 面积预剪枝：只算面积，明显离谱就不跑 PVT 仿真（省下大量评估次数）
    try:
        self.calc_area()
        a = getattr(self, 'total_area', None)
        if a and a > 0:
            if getattr(self, '_init_area', None) is None:
                self._init_area = a
            cap = AREA_CAP_FACTOR * self._init_area
            if a > cap:
                self.iter_count = getattr(self, 'iter_count', 0) + 1
                pen = 1e6 + (a / cap) * 10.0
                print('==== iter %d SKIP-SIM area %.1f > cap %.1f (pen %.1f) ===='
                      % (self.iter_count, a, cap, pen), flush=True)
                return pen
    except Exception as e:
        print('WARN: 面积预检失败（继续走仿真）: %s' % e, flush=True)

    scores = self.evaluate()

    # [P0-9] 仿真失败时上游 evaluate() 返回 ""，直接用会 KeyError 崩掉整轮
    #（参考实跑就是这样死的：log 末尾 'Phase_Margin' 后 Best parameters saved to: 空）
    if not isinstance(scores, dict) or 'Phase_Margin' not in scores:
        print('WARN: 本次仿真无效，按最差解处理（约束全违反）', flush=True)
        scores = {
            'Phase_Margin': -float('inf'), 'Gain_Margin': float('inf'),
            'Gain_db': -float('inf'), 'I_OPA': float('inf'),
            'UGB': 0.0, 'Total_Area': 1e9,
        }

    # [P0-15] 默认用赛题 6.3 口径；OPT_OBJECTIVE=score_py 可切回 score.py 口径
    if os.environ.get('OPT_OBJECTIVE', 'pdf') == 'score_py':
        score, viol = _est_score(scores)
    else:
        score, viol = _est_score_pdf(scores)
    fitness = -score + viol * 1e3

    # [P0-16] 增益硬门槛：Gain < 40dB 的候选排在所有达标解之后；
    # 若本次运行始终没有达标解，则按"离 40 还差多少"排序，best 会趋近 40。
    gain_now = scores.get('Gain_db')
    if GAIN_GATE and (gain_now is None or gain_now < GAIN_MIN_DB):
        short = GAIN_MIN_DB - (gain_now if isinstance(gain_now, (int, float)) and gain_now > -1e3 else 0.0)
        fitness += GAIN_GATE_PENALTY + short * 10.0

    self.iter_count = getattr(self, 'iter_count', 0) + 1
    print('==== iter %d fitness %.6f (score %.2f, viol %.2f) PM=%s GM=%s Gain=%s UGB=%s I=%s Area=%s'
          % (self.iter_count, fitness, score, viol,
             scores.get('Phase_Margin'), scores.get('Gain_Margin'), scores.get('Gain_db'),
             scores.get('UGB'), scores.get('I_OPA'), scores.get('Total_Area')), flush=True)

    if fitness < getattr(self, 'best_fitness', float('inf')):
        self.best_fitness = fitness
        self.best_iter = self.iter_count
        try:
            os.makedirs(self.output_path, exist_ok=True)
            # 关键：把**当前最优**参数导出到 run_score.sh 指定的 best_param_file
            extract_params(self.ae_lib, self.ae_cell, self.ae_view, self.best_param_file)
            with open(os.path.join(self.output_path, 'best_result.txt'), 'w') as bf:
                bf.write('iter        : %d\n' % self.best_iter)
                bf.write('fitness     : %s\nscore       : %s\nviol        : %s\n'
                         % (fitness, score, viol))
                for k in ('UGB', 'Phase_Margin', 'Gain_db', 'Gain_Margin', 'I_OPA', 'Total_Area'):
                    bf.write('%-12s: %s\n' % (k, scores.get(k)))
            print('==== new best: iter %d fitness %.6f' % (self.best_iter, fitness), flush=True)
        except Exception as e:
            print('WARN: 保存最优解失败: %s' % e, flush=True)
    return fitness


def _patched_run_de(self, reduced_params, max_iter=None, pop_size=None, time_limit=None):
    """预算感知的差分进化：先测 T_eval，再分配种群/代数；超时前提前停。"""
    t0 = time.time()
    n_param = len(reduced_params)
    bounds = [(0.0, 1.0)] * n_param
    init_norm = np.array([p.normalize(p.value) for _, p in reduced_params.items()], dtype=float)

    self.iter_count = getattr(self, 'iter_count', 0)
    self.best_fitness = getattr(self, 'best_fitness', float('inf'))

    # ---- P4-a：先评估初始点（测耗时），同时保证 best_param_file 一定有内容 ----
    try:
        self.optimization_objective(init_norm, reduced_params)
    except Exception as e:
        print('WARN: 初始点评估失败: %s' % e, flush=True)
    t_eval = max(time.time() - t0, 0.05)
    if not os.path.exists(self.best_param_file):
        try:
            extract_params(self.ae_lib, self.ae_cell, self.ae_view, self.best_param_file)
            print('WARN: 已按初始参数兜底写出 %s' % self.best_param_file, flush=True)
        except Exception as e:
            print('ERROR: 兜底写 best_param_file 失败: %s' % e, flush=True)

    # ---- P2：按实测耗时反推预算；并用 [P0-2] 夹到时间分满分区以内 ----
    budget = (time_limit or TIME_LIMIT_TOTAL) * BUDGET_RATIO
    cap = TIME_FULL_SCORE - TIME_SAFETY
    if budget > cap:
        print('==== [P0-2] 预算 %.0fs 超出时间分满分区，压缩到 %.0fs'
              '（满分线 %.0fs - 收尾余量 %.0fs）===='
              % (budget, cap, TIME_FULL_SCORE, TIME_SAFETY), flush=True)
        budget = cap
    remain = max(budget - (time.time() - t0), 1.0)

    # [P0-13] 不再用 t_eval 反推 pop/maxiter。
    # 实跑证据：第一次评估含 MDE 预热，t_eval 被测成 81.4s（后续实际约 20s），
    # 于是推出 pop=12/maxiter=1，DE 只跑 1 代，等于没优化。
    # 现在改为：固定种群 + 大 maxiter，由 [P0-12] 的硬截止负责按时收尾。
    pop_total = int(os.environ.get('OPT_POP', str(POP_FIXED)))
    if max_iter is None:
        max_iter = MAX_ITER_CAP
    print('\n==== BUDGET: t_eval(first,含预热)=%.1fs pop=%d maxiter=%d budget=%.0fs '
          'n_param=%d（靠硬截止收尾）===='
          % (t_eval, pop_total, max_iter, budget, n_param), flush=True)

    rng = np.random.default_rng(RANDOM_SEED)

    # [P0-13] 初值局部化 v2：**相对扰动 + 稀疏掩码**
    # 旧版问题：归一化空间 ±8% 对宽区间参数（segL 5~100、fw 0.15~50）等于实际值 ±40%，
    # 而且一次动全部 63 个参数 -> 仿真直接死（PM/UGB=-inf）。
    # 现在：每个候选只动 25% 的参数，且每个参数按"自身当前值的 ±15%"缩放。
    rel_sigma = float(os.environ.get('OPT_REL_SIGMA', str(REL_SIGMA)))
    sparse_p = float(os.environ.get('OPT_SPARSE_P', str(SPARSE_P)))
    names = list(reduced_params.keys())
    n_p = len(names)
    rows = [init_norm]
    for _ in range(max(1, pop_total - 1)):
        row = init_norm.copy()
        mask = rng.random(n_p) < sparse_p
        if not mask.any():
            mask[rng.integers(0, n_p)] = True
        for j in np.where(mask)[0]:
            p = reduced_params[names[j]]
            name = names[j]
            suffix = name.rsplit('_', 1)[-1]
            inst = name.rsplit('_', 1)[0]
            if inst[:1] in ('C', 'c') and suffix == 'l':
                # [P0-19] 电容（米勒补偿 C0/C11、CMFB 滤波 C2/C3）**只缩小**：
                # 电容变小 -> 补偿电容变小 -> UGB 上升，同时面积下降（双赢）
                v = p.value * (1.0 - abs(rng.uniform(0.0, rel_sigma)))
            elif suffix in UP_ONLY_SUFFIX:
                # 增益导向：MOS 只放大 l / fw（抬高 ro 与 gm）
                v = p.value * (1.0 + abs(rng.uniform(0.0, rel_sigma)))
            else:
                v = p.value * (1.0 + rng.uniform(-rel_sigma, rel_sigma))
            v = min(max(v, p.min), p.max)
            row[j] = p.normalize(v)
        rows.append(row)
    init = np.clip(np.array(rows, dtype=float), 0.0, 1.0)
    init[0] = init_norm
    print('==== [P0-13] 初值局部化：相对扰动 %.0f%% / 每次只动 %.0f%% 的参数 ===='
          % (rel_sigma * 100, sparse_p * 100), flush=True)

    deadline = t0 + budget
    self._deadline = deadline          # [P0-12] 供 objective 内做硬截止检查

    def _cb(xk, convergence=None):
        if time.time() > deadline:
            print('==== 时间预算到达，提前结束 ====', flush=True)
            return True
        return False

    try:
        result = differential_evolution(
            func=lambda x: self.optimization_objective(x, reduced_params),
            bounds=bounds,
            init=init,
            maxiter=max_iter,
            tol=0.0,
            mutation=(0.5, 1.0),
            recombination=0.7,
            strategy='best1bin',
            polish=False,
            workers=1,
            callback=_cb,
        )
        print('\n==== DE done: success=%s fun=%.6f nit=%s ===='
              % (result.success, result.fun, getattr(result, 'nit', '?')), flush=True)
        try:
            real_values = self.denormalize_values(reduced_params, result.x)
            os.makedirs(self.output_path, exist_ok=True)
            with open(os.path.join(self.output_path, 'optimized_params.txt'), 'w') as f:
                for i, (name, _p) in enumerate(reduced_params.items()):
                    f.write('%s: %s\n' % (name, _p.format_value(real_values[i])))
        except Exception as e:
            print('WARN: 写 optimized_params.txt 失败: %s' % e, flush=True)
    except Exception as e:
        print('\n==== DE 异常退出（保留当前最优）: %s ====' % e, flush=True)

    # ---- P4-b：收尾再写一次，确保文件存在且为最优 ----
    try:
        if getattr(self, 'best_fitness', float('inf')) < float('inf'):
            extract_params(self.ae_lib, self.ae_cell, self.ae_view, self.best_param_file)
    except Exception as e:
        print('WARN: 收尾写 best_param_file 失败: %s' % e, flush=True)
    print('==== TOTAL: %.1fs, iters=%d, best_param_file=%s(存在=%s) ===='
          % (time.time() - t0, getattr(self, 'iter_count', 0), self.best_param_file,
             os.path.exists(self.best_param_file)), flush=True)


def _patched_main():
    args = parse_arguments()
    if getattr(args, 'verbose', False):
        print('[VERBOSE] args = %s' % vars(args))

    # [P0-8] 必须在 emyInitAether / MdeSession.open 之前把旧机绝对路径修好
    try:
        _fix_sim_paths()
    except Exception as e:
        print('WARN: [P0-8] 模型路径修复异常（继续跑）: %s' % e, flush=True)

    ae.emyInitAether('-adv')

    # ---- P1：默认使用模块二的约减分组（CLI 有传就以 CLI 为准）----
    # [P0-5] 分组按本电路实际存在的器件过滤；一个都没匹配上就退化为全独立变量，
    #        绝不对 Hidden 电路硬套 case1 的分组（宁可维度高，不可分组错）。
    raw_all = read_parameters(args.param_file, [])
    if os.environ.get('OPT_NO_REDUCTION', '0') == '1':
        print('==== [P0-5] OPT_NO_REDUCTION=1：关闭模块二分组，全部变量独立优化 ====',
              flush=True)
        dummy_arg, sym_arg = '', ''
    else:
        dummy_arg, sym_arg = _filter_groups(
            raw_all,
            args.dummy_devices or DEFAULT_DUMMY_DEVICES,
            args.symmetry_devices or DEFAULT_SYMMETRY_DEVICES)
    print('==== 约减配置（来自模块二，已按本电路过滤）====')
    print('  dummy_devices    : %s' % (dummy_arg or '(无)'))
    print('  symmetry_devices : %s' % (sym_arg or '(无)'))
    if not dummy_arg and not sym_arg:
        print('==== [P0-5] 本电路未匹配到模块二分组 -> 退化为全独立变量'
              '（安全，但搜索维度更高）====', flush=True)

    dummy_devices = [d for d in dummy_arg.split(',') if d]
    parameters = read_parameters(args.param_file, dummy_devices)
    non_dummy_params = {n: p for n, p in parameters.items() if not p.is_dummy}
    dummy_params = {n: p for n, p in parameters.items() if p.is_dummy}
    print('==== dummy params: %d | 待优化参数: %d ====' % (len(dummy_params), len(non_dummy_params)))

    symmetry_constraints = parse_symmetry_constraints(sym_arg)
    if symmetry_constraints:
        reduced_parameters, param_mapping = apply_symmetry_constraints(non_dummy_params, symmetry_constraints)
    else:
        reduced_parameters, param_mapping = non_dummy_params, None

    platform = SimulatePlatform(
        ae_lib=args.ae_lib, ae_cell=args.ae_cell, ae_view=args.ae_view,
        mde_cell=args.mde_cell, mde_view=args.mde_view,
        output_path=args.output_path, output_file=args.output_file,
        best_param_file=args.best_param_file,
        symmetry_constraints=symmetry_constraints, dummy_params=dummy_params)

    platform.param_mapping = param_mapping
    if param_mapping:
        platform.reverse_mapping = {}
        for orig, red in param_mapping.items():
            platform.reverse_mapping.setdefault(red, []).append(orig)

    # 用补丁版方法覆盖（不动原类）
    platform.optimization_objective = types.MethodType(_patched_objective, platform)
    platform.run_de_optimization = types.MethodType(_patched_run_de, platform)

    # ---- 冒烟测试：--set_params/--evaluate 只跑一次仿真并打印指标（不优化）----
    if getattr(args, 'set_params', False) or getattr(args, 'evaluate', False):
        print('\n==== SINGLE-EVAL MODE（只评估一次，不优化）====', flush=True)
        try:
            os.makedirs(args.output_path, exist_ok=True)
        except Exception:
            pass
        try:
            platform.only_set_params(parameters)
            scores = platform.evaluate()
            print('==== scores: %s ====' % scores, flush=True)
            try:
                extract_params(args.ae_lib, args.ae_cell, args.ae_view, args.best_param_file)
                print('==== 已写出 %s ====' % args.best_param_file, flush=True)
            except Exception as e:
                print('WARN: 写 best_param_file 失败: %s' % e, flush=True)
        except Exception as e:
            print('ERROR: 单次评估失败: %s' % e, flush=True)
        return

    platform.run_de_optimization(reduced_parameters, max_iter=None, pop_size=None)


if __name__ == "__main__":
    try:
        _patched_main()
    except Exception as exc:
        import traceback
        traceback.print_exc()
        print('FATAL: 优化流程异常，尝试按初始参数兜底写出 best_param_file', flush=True)
        try:
            _a = parse_arguments()
            ae.emyInitAether('-adv')
            read_parameters(_a.param_file, [])
            extract_params(_a.ae_lib, _a.ae_cell, _a.ae_view, _a.best_param_file)
            print('FALLBACK OK: %s' % _a.best_param_file, flush=True)
        except Exception as e2:
            print('FALLBACK FAILED: %s' % e2, flush=True)
