#!/bin/bash

# Set color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Print colored information
print_info() {
    echo -e "${BLUE}[INFO]${NC} $1" >&2
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1" >&2
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1" >&2
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1" >&3
}

# Parse command line arguments
COMPRESSED_FILE=""
TIME_LIMIT="10800"  # Default 3 hours
SCORE_SCRIPT="./score.py"
OPTIMIZATION_SCRIPT="optimization.py"
EXTRA_ARGS=()

# Set parameters based on input filename
setup_parameters() {
    local compressed_file="$1"
    local filename=$(basename "$compressed_file")
    
    print_info "Analyzing filename: $filename"
    
    if [[ "$filename" == *"eda_2026_case_1"* ]]; then
        AE_LIB="2026_EDA_case1"
        INPUT_PARAM_FILE="case1_params_0.txt"
        UGB_BASE=200000000.0
        AREA_BASE=8000.0
        print_info "Set to case1 parameters: AE_LIB=$AE_LIB, INPUT_PARAM_FILE=$INPUT_PARAM_FILE"
       else
        print_error "Unrecognized filename: $filename"
        print_error "Filename should contain 'eda_2026_case_1' "
        exit 1
    fi
}

# Set pyAether required lib parameters
AE_LIB=""
AE_CELL="OPA"
AE_VIEW="schematic"
MDE_CELL="OPA_loopgain"
MDE_VIEW="spe_state1_Corner"

# Set scoring cell and view, these parameters cannot be changed by user
SCORE_MDE_CELL="OPA_loopgain"
SCORE_MDE_VIEW="spe_state1_Corner"

# Set input parameter filename
INPUT_PARAM_FILE=""

# Set output path and filename
OUTPUT_PATH="./case_results"
OUTPUT_FILE="output.log"

# Set scoring related parameters
TIME_BASE=7200.0
UGB_BASE=1e8  # Default value, will be overwritten in setup_parameters
AREA_BASE=5e5 # Default value, will be overwritten in setup_parameters

# Show usage
show_usage() {
    echo "Usage: $0 [OPTIONS] <compressed_file_path>"
    echo ""
    echo "Options:"
    echo "  -h, --help                Show this help message"
    echo "  -o, --output-dir DIR      Specify extraction directory (default: current directory)"
    echo "  -t, --time-limit SECONDS  Set timeout in seconds"
    echo "  --score-script PATH       Specify scoring script path (default: ./score.py)"
    echo "  --opt-script NAME         Specify optimization script name (default: optimization.py)"
    echo "  --                        Separator, arguments after this are passed to score.py"
    echo ""
    echo "Examples:"
    echo "  $0 optimization_package.tar.gz"
    echo "  $0 -o ./output -t 7200 optimization_package.tar.gz"
    echo "  $0 optimization_package.tar.gz -- --time-limit 3600"
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_usage
            exit 0
            ;;
        -o|--output-dir)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        -t|--time-limit)
            TIME_LIMIT="$2"
            shift 2
            ;;
        --score-script)
            SCORE_SCRIPT="$2"
            shift 2
            ;;
        --opt-script)
            OPTIMIZATION_SCRIPT="$2"
            shift 2
            ;;
        --)
            shift
            EXTRA_ARGS=("$@")
            break
            ;;
        -*)
            print_error "Unknown option: $1"
            show_usage
            exit 1
            ;;
        *)
            COMPRESSED_FILE="$1"
            shift
            ;;
    esac
done

# Check required parameters
if [[ -z "$COMPRESSED_FILE" ]]; then
    print_error "Compressed file path must be specified"
    show_usage
    exit 1
fi

# Set parameters (called after parsing arguments)
setup_parameters "$COMPRESSED_FILE"

# Check if compressed file exists
if [[ ! -f "$COMPRESSED_FILE" ]]; then
    print_error "Compressed file does not exist: $COMPRESSED_FILE"
    exit 1
fi

# Check if scoring script exists
if [[ ! -f "$SCORE_SCRIPT" ]]; then
    print_error "Scoring script does not exist: $SCORE_SCRIPT"
    exit 1
fi

# Check ae_cell
if [[ "$AE_CELL" != "OPA" ]]; then
    print_error "Unsupported ae_cell: $AE_CELL"
    exit 1
fi

# Check ae_view
if [[ "$AE_VIEW" != "schematic" ]]; then
    print_error "Unsupported ae_view: $AE_VIEW"
    exit 1
fi

# Read parameters from command.txt file (moved after setup_parameters)
COMMAND_FILE="/app/input/res/command.txt"
if [[ -f "$COMMAND_FILE" ]]; then
    print_info "Reading parameters from file: $COMMAND_FILE"
    
    # Read current case type
    CURRENT_CASE=""
    if [[ "$AE_LIB" == "2026_EDA_case1" ]]; then
        CURRENT_CASE="case1"
    fi
    
    if [[ -n "$CURRENT_CASE" ]]; then
        print_info "Current case: $CURRENT_CASE"
        
        # Find corresponding case parameters
        in_target_case=false
        while IFS= read -r line || [[ -n "$line" ]]; do
            # Clean line content
            line_cleaned=$(echo "$line" | sed 's/\r$//' | sed 's/^[[:space:]]*//' | sed 's/[[:space:]]*$//')
            
            # Skip empty lines
            if [[ -z "$line_cleaned" ]]; then
                continue
            fi
            
            # Check if it's a case marker
            if [[ "$line_cleaned" == "case1"  ]]; then
                if [[ "$line_cleaned" == "$CURRENT_CASE" ]]; then
                    in_target_case=true
                    print_info "Found target case configuration: $CURRENT_CASE"
                else
                    in_target_case=false
                fi
                continue
            fi
            
            # If in target case block, parse parameters
            if [[ "$in_target_case" == true ]]; then
                case "$line_cleaned" in
                    --mde_cell*)
                        MDE_CELL=$(echo "$line_cleaned" | awk '{$1=""; print $0}' | sed 's/^[[:space:]]*//' | sed 's/[[:space:]]*$//')
                        print_info "Set MDE_CELL: '$MDE_CELL'"
                        ;;
                    --mde_view*)
                        MDE_VIEW=$(echo "$line_cleaned" | awk '{$1=""; print $0}' | sed 's/^[[:space:]]*//' | sed 's/[[:space:]]*$//')
                        print_info "Set MDE_VIEW: '$MDE_VIEW'"
                        ;;
                esac
            fi
        done < "$COMMAND_FILE"
    else
        print_warning "Cannot determine current case type, using default parameters"
    fi
else
    print_warning "Parameter file does not exist: $COMMAND_FILE, using default parameters"
fi

run_optimization_with_timeout() {
    local script_name="$1"
    local timeout_seconds="$2"
    local start_time
    local end_time
    local execution_time
    local timed_out=0
    
    print_info "Starting optimization script: $script_name"
    start_time=$(date +%s)
    
    # Create log file
    local log_file="${AE_LIB}_optimization.log"
    
    # Start optimization script with independent process group
    local start_cmd
    if command -v taskset >/dev/null 2>&1; then
        print_info "Using taskset to limit CPU cores: 1-10"
        start_cmd="taskset -c 1-10 pythone \"$script_name\""
    else
        start_cmd="pythone \"$script_name\""
    fi
    
    # Complete start command
    start_cmd="$start_cmd --ae_lib \"${AE_LIB}\" --ae_cell \"${AE_CELL}\" --ae_view \"${AE_VIEW}\" --mde_cell \"${MDE_CELL}\" --mde_view \"${MDE_VIEW}\" --param_file \"${INPUT_PARAM_FILE}\" --best_param_file \"${AE_LIB}_best_params.txt\""
    
    print_info "Start command: $start_cmd"
    
    # Use setsid to create new session and process group
    if command -v setsid >/dev/null 2>&1; then
        print_info "Using setsid to create independent process group"
        setsid bash -c "$start_cmd > \"$log_file\" 2>&1" &
    else
        # If setsid not available, use nohup and start in subshell
        print_info "Using nohup to start process"
        nohup bash -c "$start_cmd" > "$log_file" 2>&1 &
    fi
    
    local opt_pid=$!
    print_info "Optimization process PID: $opt_pid"
    
    # Get process group ID (PGID)
    local pgid
    if ps -p $opt_pid >/dev/null 2>&1; then
        pgid=$(ps -o pgid= -p $opt_pid 2>/dev/null | tr -d ' ')
        print_info "Process Group ID (PGID): $pgid"
    else
        print_warning "Cannot get process group ID, using PID as PGID"
        pgid=$opt_pid
    fi
    
    # Verify process status
    sleep 2
    if ! ps -p $opt_pid >/dev/null 2>&1; then
        print_error "Optimization process has exited, please check log file: $log_file"
        if [[ -f "$log_file" ]]; then
            print_error "Log file content:"
            cat "$log_file" >&2
        fi
        echo "0 1"
        return
    fi
    
    # Wait for process completion or timeout
    local waited=0
    while [[ $waited -lt $timeout_seconds ]]; do
        if ! ps -p $opt_pid >/dev/null 2>&1; then
            break
        fi
        sleep 1
        waited=$((waited + 1))
        echo -n "." >&2
        if [[ $((waited % 60)) -eq 0 ]]; then
            echo "" >&2
            print_info "Elapsed: ${waited} seconds ($(($waited/60)) minutes), remaining: $(($timeout_seconds - $waited)) seconds"
        fi
    done

    echo "" >&2
    
    # Timeout handling
    if ps -p $opt_pid >/dev/null 2>&1; then
        print_warning "Optimization script timeout, terminating process..."
        print_info "Terminating process group: $pgid (PID: $opt_pid)"
        
        # Only terminate specific process group, not current script's process group
        if [[ -n "$pgid" ]] && [[ "$pgid" != "$$" ]] && [[ "$pgid" != $(ps -o pgid= -p $$ | tr -d ' ') ]]; then
            # Use kill to send signal to specific process group
            if kill -TERM -$pgid 2>/dev/null; then
                print_info "Sent TERM signal to process group: -$pgid"
            else
                print_warning "Cannot terminate process group $pgid, trying to terminate single process"
                kill -TERM $opt_pid 2>/dev/null
            fi
        else
            print_warning "PGID same as current script, only terminating single process"
            kill -TERM $opt_pid 2>/dev/null
        fi
        
        # Wait for process to end
        local kill_wait=0
        while [[ $kill_wait -lt 5 ]] && ps -p $opt_pid >/dev/null 2>&1; do
            sleep 1
            kill_wait=$((kill_wait + 1))
        done
        
        # If process still exists, force kill
        if ps -p $opt_pid >/dev/null 2>&1; then
            print_warning "Process still not terminated, forcing kill..."
            if [[ -n "$pgid" ]] && [[ "$pgid" != "$$" ]] && [[ "$pgid" != $(ps -o pgid= -p $$ | tr -d ' ') ]]; then
                kill -KILL -$pgid 2>/dev/null
            else
                kill -KILL $opt_pid 2>/dev/null
            fi
        fi
        
        timed_out=1
        end_time=$(date +%s)
        execution_time=$timeout_seconds
    else
        # Process ended normally
        wait $opt_pid 2>/dev/null
        local exit_code=$?
        end_time=$(date +%s)
        execution_time=$((end_time - start_time))
        
        if [[ $exit_code -eq 0 ]]; then
            print_success "Optimization script ended normally"
        else
            print_warning "Optimization script ended abnormally, exit code: $exit_code"
        fi
    fi

    # Format execution time
    local hours=$((execution_time / 3600))
    local minutes=$(( (execution_time % 3600) / 60 ))
    local seconds=$((execution_time % 60))
    local formatted_time=$(printf "%02d:%02d:%02d" $hours $minutes $seconds)
    
    print_info "Execution duration: $formatted_time ($execution_time seconds)"
    print_info "Timed out: $([[ $timed_out -eq 1 ]] && echo "Yes" || echo "No")"

    echo "$execution_time $timed_out"
}

OUTPUT_DIR="./${AE_LIB}_output"

print_info "Starting optimization environment setup..."
print_info "Compressed file: $COMPRESSED_FILE"
print_info "Output directory: $OUTPUT_DIR"
print_info "Scoring script: $SCORE_SCRIPT"
print_info "Optimization script: $OPTIMIZATION_SCRIPT"
print_info "Time limit: $TIME_LIMIT seconds ($(($TIME_LIMIT/3600)) hours)"
print_info "Circuit under test: $AE_LIB"
print_info "UGB  baseline: $UGB_BASE"
print_info "AREA baseline: $AREA_BASE"
print_info "TIME baseline: $TIME_BASE"

# Check if output directory exists and remove it
if [[ -d "$OUTPUT_DIR" ]]; then
    print_warning "Output directory already exists: $OUTPUT_DIR"
    print_info "Removing existing output directory..."
    rm -rf "$OUTPUT_DIR"
    if [[ $? -ne 0 ]]; then
        print_error "Failed to remove existing output directory: $OUTPUT_DIR"
        exit 1
    fi
    print_success "Existing output directory removed successfully"
fi

# Create output directory
print_info "Creating output directory: $OUTPUT_DIR"
mkdir -p "$OUTPUT_DIR"
if [[ $? -ne 0 ]]; then
    print_error "Failed to create output directory: $OUTPUT_DIR"
    exit 1
fi

# Extract file
print_info "Extracting file..."
if [[ "$COMPRESSED_FILE" == *.tar.gz ]] || [[ "$COMPRESSED_FILE" == *.tgz ]]; then
    tar -xzf "$COMPRESSED_FILE" -C "$OUTPUT_DIR"
elif [[ "$COMPRESSED_FILE" == *.tar ]]; then
    tar -xf "$COMPRESSED_FILE" -C "$OUTPUT_DIR"
elif [[ "$COMPRESSED_FILE" == *.zip ]]; then
    unzip -q "$COMPRESSED_FILE" -d "$OUTPUT_DIR"
else
    print_error "Unsupported compression format: $COMPRESSED_FILE"
    print_info "Supported formats: .tar.gz, .tgz, .tar, .zip"
    exit 1
fi

if [[ $? -ne 0 ]]; then
    print_error "Failed to extract file"
    exit 1
fi

print_success "File extraction completed"

# Find extracted directory (handle possible multi-level directory structure)
EXTRACTED_DIR="$OUTPUT_DIR"

# Get base name of compressed file (without extension)
COMPRESSED_BASENAME=$(basename "$COMPRESSED_FILE")
COMPRESSED_NAME="${COMPRESSED_BASENAME%.*}"
COMPRESSED_NAME="${COMPRESSED_NAME%.tar}"  # Handle .tar.gz case

print_info "Compressed file base name: $COMPRESSED_NAME"

# First check if directory with same name as compressed file exists
if [[ -d "$OUTPUT_DIR/$COMPRESSED_NAME" ]]; then
    EXTRACTED_DIR="$OUTPUT_DIR/$COMPRESSED_NAME"
    print_info "Found directory with same name: $EXTRACTED_DIR"
# If only one directory after extraction, use that directory
elif [[ $(find "$OUTPUT_DIR" -maxdepth 1 -type d | wc -l) -eq 2 ]]; then
    SUBDIR=$(find "$OUTPUT_DIR" -maxdepth 1 -type d ! -path "$OUTPUT_DIR")
    if [[ -n "$SUBDIR" ]]; then
        EXTRACTED_DIR="$SUBDIR"
        print_info "Using unique subdirectory: $EXTRACTED_DIR"
    fi
else
    print_info "Files extracted directly to output directory: $EXTRACTED_DIR"
fi

# Copy scoring script
print_info "Copying scoring script to working directory..."
cp "$SCORE_SCRIPT" "$EXTRACTED_DIR/"
if [[ $? -ne 0 ]]; then
    print_error "Failed to copy scoring script"
    exit 1
fi

print_success "Scoring script copied successfully"

# Copy circuits
print_info "Copying test circuits to working directory..."
cp -rf circuits/* "$EXTRACTED_DIR/"
if [[ $? -ne 0 ]]; then
    print_error "Failed to copy test circuits"
    exit 1
fi

print_success "Test circuits copied successfully"

# Change to working directory
print_info "Changing to working directory: $EXTRACTED_DIR"
cd "$EXTRACTED_DIR" || {
    print_error "Cannot change to working directory: $EXTRACTED_DIR"
    exit 1
}

# Check if optimization script exists
if [[ ! -f "$OPTIMIZATION_SCRIPT" ]]; then
    print_error "Optimization script does not exist: $OPTIMIZATION_SCRIPT"
    exit 1
fi

# Run optimization script and get execution time
print_info "Starting optimization script monitoring..."
result=$(run_optimization_with_timeout "$OPTIMIZATION_SCRIPT" "$TIME_LIMIT")

# Parse execution time and timeout status
execution_time=$(echo $result | awk '{print $1}')
timed_out=$(echo $result | awk '{print $2}')

echo ""
print_info "Optimization script execution completed, starting scoring program..."

# Build execution command
CMD=("pythone" "score.py")

# Add lib/cell/view
CMD+=("--ae_lib" "${AE_LIB}")
CMD+=("--ae_cell" "${AE_CELL}")
CMD+=("--ae_view" "${AE_VIEW}")
CMD+=("--mde_cell" "${SCORE_MDE_CELL}")
CMD+=("--mde_view" "${SCORE_MDE_VIEW}")

# Add input, output parameters
CMD+=("--best_param_file" "${AE_LIB}_best_params.txt")
CMD+=("--output_path" "${OUTPUT_PATH}")
CMD+=("--output_file" "${OUTPUT_FILE}")

# Add scoring related parameters
CMD+=("--calc_score")
CMD+=("--ugb_base" "${UGB_BASE}")
CMD+=("--area_base" "${AREA_BASE}")
CMD+=("--time_base" "${TIME_BASE}")

# Add execution time parameter
CMD+=("--execution_time" "$execution_time")

# Add extra parameters
if [[ ${#EXTRA_ARGS[@]} -gt 0 ]]; then
    CMD+=("${EXTRA_ARGS[@]}")
fi

print_info "Execution command: ${CMD[*]}"
echo ""

# Execute scoring program
"${CMD[@]}"

EXIT_CODE=$?

echo ""
if [[ $EXIT_CODE -eq 0 ]]; then
    print_success "Scoring program execution completed"
else
    print_warning "Scoring program exit code: $EXIT_CODE"
fi

# Return to original directory (optional)
cd /app/program/

print_info "Working directory: $EXTRACTED_DIR"
print_info "Please check the above directory for result files"
