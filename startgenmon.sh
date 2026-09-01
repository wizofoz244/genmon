#!/bin/bash
# bash script to start, stop or restart genmon. the scrip calls genloader.py
# with the needed command line parameters and can use python 2.7 or 3.x to call
# genloader.py
#-------------------------------------------------------------------------------
PARAMS=""
genmondir="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
pythoncommand="python3"
pipcommand="pip3"
config_path=""
usepython3=true
found_action=false
managedpackages=false
RESET_TAILSCALE=false


#-------------------------------------------------------------------------------
function env_activate() {

  if [ "$managedpackages" = true ] ; then
    source $genmondir/genenv/bin/activate
  fi
}
#-------------------------------------------------------------------------------
function env_deactivate() {
  if [ "$managedpackages" = true ] ; then
    deactivate
  fi
}
#-------------------------------------------------------------------------------
function checkmanagedpackages() {

  #  /usr/lib/python3.11/EXTERNALLY-MANAGED
  pythonmajor=$($pythoncommand -c 'import sys; print(sys.version_info.major)')
  pythonminor=$($pythoncommand -c 'import sys; print(sys.version_info.minor)')
  managedfile="/usr/lib/python$pythonmajor.$pythonminor/EXTERNALLY-MANAGED"

  if [ -f $managedfile ]; then
      pythoncommand="$genmondir/genenv/bin/python"
      managedpackages=true
      echo "using binary: $pythoncommand"
  fi
}
#-------------------------------------------------------------------------------
function setuppython3() {

  if [ $# -eq 0 ]; then
    usepython3=false
  elif [ $1 == "3" ]; then
    usepython3=true
  elif [ $1 == "2" ]; then
    usepython3=false
  else
    usepython3=false
  fi

  if [ "$usepython3" = true ] ; then
    echo 'Using Python 3.x...'
    pipcommand="pip3"
    pythoncommand="python3"
  else
    echo 'Using Python 2.x...'
    pipcommand="pip2"
    pythoncommand="python2"
fi
}

#-------------------------------------------------------------------------------
function get_genmon_conf_value() {
  local key="$1"
  local default_val="$2"
  local conf_file="/etc/genmon/genmon.conf"
  if [ -n "$config_path" ]; then
    local custom_dir=$(echo "$config_path" | awk '{print $2}')
    if [ -f "$custom_dir/genmon.conf" ]; then
      conf_file="$custom_dir/genmon.conf"
    fi
  elif [ ! -f "$conf_file" ] && [ -f "$genmondir/conf/genmon.conf" ]; then
    conf_file="$genmondir/conf/genmon.conf"
  fi

  if [ -f "$conf_file" ]; then
    local val=$(grep -E "^[[:space:]]*$key[[:space:]]*=" "$conf_file" 2>/dev/null | tail -n 1 | cut -d'=' -f2- | tr -d ' \r\n\t')
    if [ -n "$val" ]; then
      echo "$val"
      return
    fi
  fi
  echo "$default_val"
}

#-------------------------------------------------------------------------------
function tailscale_sync() {
  local action="$1"
  if ! command -v tailscale &>/dev/null; then
    return
  fi

  local usehttps=$(get_genmon_conf_value "usehttps" "False")
  local target_port="8000"
  local target_proto="http"

  if [[ "$usehttps" =~ ^[Tt][Rr][Uu][Ee]$ ]]; then
    local https_port=$(get_genmon_conf_value "https_port" "8443")
    target_port="$https_port"
    target_proto="https+insecure"
  else
    local http_port=$(get_genmon_conf_value "http_port" "8000")
    target_port="$http_port"
    target_proto="http"
  fi

  case "$action" in
    start|restart)
      local expected="proxy $target_proto://127.0.0.1:$target_port"
      if [ "$RESET_TAILSCALE" = true ] || ! tailscale funnel status 2>/dev/null | grep -Fq "$expected"; then
        echo "Synchronizing Tailscale Funnel to $target_proto://127.0.0.1:$target_port..."
        sudo tailscale funnel reset 2>/dev/null || true
        sudo tailscale serve reset 2>/dev/null || true
        sudo tailscale funnel --bg "$target_proto://127.0.0.1:$target_port" 2>/dev/null || true
      else
        echo "Tailscale Funnel already active on $target_proto://127.0.0.1:$target_port (skipping reset; use -t or --tailscale-reset to force)."
      fi
      ;;
    stop|hardstop)
      echo "Stopping Tailscale Funnel..."
      sudo tailscale funnel reset 2>/dev/null || true
      sudo tailscale serve reset 2>/dev/null || true
      ;;
  esac
}

#-------------------------------------------------------------------------------
function verify_and_show_status() {
  echo ""
  echo "=================================================================="
  echo "           🚦 Genmon System Process Status Verification           "
  echo "=================================================================="
  sleep 3

  local core_procs=("genmon.py" "genserv.py")
  local all_procs=("genmon.py" "genserv.py" "genwebpush.py" "genpushover.py" "genmqtt.py" "gengpio.py")
  local failed_count=0
  local running_count=0

  for proc in "${all_procs[@]}"; do
    local pids=$(pgrep -f "$proc" 2>/dev/null | tr '\n' ' ')
    if [ -n "$pids" ]; then
      printf "  %-20s 🟢 [ \033[1;32mRUNNING\033[0m ]  (PID: %s)\n" "$proc" "$pids"
      running_count=$((running_count + 1))
    else
      if [[ " ${core_procs[*]} " =~ " ${proc} " ]]; then
        printf "  %-20s 🔴 [ \033[1;31mSTOPPED / FAILED\033[0m ]\n" "$proc"
        failed_count=$((failed_count + 1))
      else
        printf "  %-20s ⚪ [ \033[0;37mINACTIVE / OFF\033[0m ]\n" "$proc"
      fi
    fi
  done

  # Tailscale Funnel / Remote Access status check
  if command -v tailscale &>/dev/null; then
    local ts_status=$(tailscale funnel status 2>/dev/null)
    local ts_url=$(echo "$ts_status" | grep -E "^https://" | awk '{print $1}' | head -n 1)
    local ts_target=$(echo "$ts_status" | grep -E "proxy " | awk '{print $NF}' | head -n 1)

    if [[ "$ts_status" == *"Funnel on"* ]] && [ -n "$ts_url" ]; then
      printf "  %-20s 🟢 [ \033[1;32mACTIVE / ON\033[0m ]  (%s -> %s)\n" "tailscale funnel" "$ts_url" "$ts_target"
      running_count=$((running_count + 1))
    elif [[ "$ts_status" == *"tailnet only"* ]] && [ -n "$ts_url" ]; then
      printf "  %-20s 🟡 [ \033[1;33mTAILNET ONLY\033[0m ] (%s -> %s)\n" "tailscale serve" "$ts_url" "$ts_target"
      running_count=$((running_count + 1))
    elif pgrep -x tailscaled &>/dev/null; then
      printf "  %-20s ⚪ [ \033[0;37mDAEMON ONLY / OFF\033[0m ] (Funnel inactive)\n" "tailscale funnel"
    else
      printf "  %-20s 🔴 [ \033[1;31mSTOPPED / OFF\033[0m ]\n" "tailscale"
    fi
  fi

  echo "=================================================================="
  if [ $failed_count -gt 0 ]; then
    echo " 🔴 WARNING: $failed_count core process(es) failed to start or remain running."
    if [ -f "/var/log/genserv.log" ]; then
      echo ""
      echo " --- Last 5 lines from /var/log/genserv.log ---"
      tail -n 5 /var/log/genserv.log 2>/dev/null
    fi
  else
    echo " 🟢 Status Verification Complete: $running_count process(es) active and running."
  fi
  echo ""
}

#-------------------------------------------------------------------------------
function clean_pycache() {
  echo "Clearing Python bytecode cache (*.pyc and __pycache__)..."
  find "$genmondir" -name "*.pyc" -delete 2>/dev/null || true
  find "$genmondir" -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
}

#-------------------------------------------------------------------------------
function printhelp(){
  echo "usage: "
  echo " "
  echo "./startgenmon.sh <options> start|stop|restart|hardstop|status|clearcache"
  echo ""
  echo "valid options:"
  echo "   -h      display help"
  echo "   -c      path of config files"
  echo "   -p      Specify 2 or 3 for python version. 3 is default"
  echo "   -k      Clear Python bytecode cache (__pycache__ / .pyc) before execution"
  echo "   -t      Force Tailscale Funnel and Serve reset on start/restart"
  echo ""
}

#-------------------------------------------------------------------------------
# main
while (( "$#" )); do
  case "$1" in
    -p)
      setuppython3 $2
      shift 2
      ;;
    -c)
      if [ -n "$2" ] && [ ${2:0:1} != "-" ]; then
        config_path="-c $2"
        shift 2
      else
        echo "Error: Argument for $1 is missing" >&2
        exit 1
      fi
      ;;
    -k|--clean|--clear-cache)
      clean_pycache
      shift
      ;;
    -t|--tailscale-reset)
      RESET_TAILSCALE=true
      shift
      ;;
    -h)
     printhelp
     exit 0
    ;;
    -*|--*=) # unsupported flags
      echo "Error: Unsupported flag $1" >&2
      exit 1
      ;;
    *) # preserve positional arguments
      PARAMS="$PARAMS $1"
      shift
      ;;
  esac
done
checkmanagedpackages
for val in $PARAMS; do
  case "$val" in
    start)
      echo "Starting genmon python scripts..."
      env_activate
      found_action=true
      sudo $pythoncommand "$genmondir/genloader.py" -s $config_path
      env_deactivate
      tailscale_sync start
      verify_and_show_status
      ;;
    stop)
      found_action=true
      env_activate
      echo "Stopping genmon python scripts..."
      sudo $pythoncommand "$genmondir/genloader.py" -x $config_path
      env_deactivate
      tailscale_sync stop
      ;;
    hardstop)
      found_action=true
      env_activate
      echo "Hard Stopping genmon python scripts..."
      sudo $pythoncommand "$genmondir/genloader.py" -z $config_path
      env_deactivate
      tailscale_sync hardstop
      ;;
    restart)
      found_action=true
      clean_pycache
      env_activate
      echo "Restarting genmon python scripts..."
      sudo $pythoncommand "$genmondir/genloader.py" -r $config_path
      env_deactivate
      tailscale_sync restart
      verify_and_show_status
      ;;
    clearcache|clean)
      found_action=true
      clean_pycache
      ;;
    status)
      found_action=true
      verify_and_show_status
      ;;
    *)
      #
      echo "Additional command found: " $val
      ;;
  esac
done

if [ "$found_action" = false ] ; then
  echo "Invalid command. Valid commands are start, stop, restart, hardstop, status, or clearcache."
fi

exit 0
