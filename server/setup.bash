#
# Empyrean setup file for "bash"
#
# NOTE: INSTALL_PATH is the name of installation;
#       LICENSE_HOST is the license server's hostname (or IP address);
#       LICENSE_PORT is a port number between 1024 and 65535
#

#if [[ $?LM_LICENSE_FILE ]]; then
#    export LM_LICENSE_FILE=<LICENSE_PORT>@<LICENSE_HOST>:$LM_LICENSE_FILE
#else
#    export LM_LICENSE_FILE=<LICENSE_PORT>@<LICENSE_HOST>
#fi
if [ $?LM_LICENSE_FILE ]; then
#  export LM_LICENSE_FILE=59001@hug01
  export LM_LICENSE_FILE=59001@172.21.170.32
else
  export LM_LICENSE_FILE=59001@172.21.170.32
fi


#export PKG_ROOT=<INSTALL_PATH>
export PKG_ROOT=/home/PyAether_Packages/tools_2509sp2
export AETHER_NAME=Aether_2025.09.sp2_linux-x86_64_rh6_20260202
export ALPS_NAME=ALPS_2025.09_linux-x86_64_rh6_20251021

export IWAVE_NAME=iWave_2025.09.sp1.hf3_linux-x86_64_rh6_20260529
#export ALPSCD_NAME=

export RCEXPLORER_NAME=RCExplorer_2026.03.hf1_linux26-x86_64_rh6_20260615

export ARGUS_NAME=argusIC_2025.06.hf5_from_hf3_linux-x86_64_rh6_20250904

#export ADA_NAME=ADA_2024.09_linux26-x86_64-el6_20240924
#export PATRON_NAME=Patron_2025.03_linux-x86_64-el6_20250326
#export ANDESPOWER_NAME=andespm_2025.03_linux-x86_64_rhel6_20250324

#aether exportup
export AETHER_ROOT=$PKG_ROOT/$AETHER_NAME
export AETHER_HOME=$AETHER_ROOT/tools/aether
export AETHER_OA_HOME=$AETHER_ROOT/openaccess
export PATH=$AETHER_ROOT/bin:$PATH

#py
#export PYAE_VER=<xxx>
export PYAE_VER=3.9
export PYPLATFORM=linux26-x86_64
export PYAETHER_HOME=$AETHER_ROOT/tools/pyaether

#alpsIC exportup
export ALPS_ROOT=$PKG_ROOT/$ALPS_NAME
export ALPS_HOME=$ALPS_ROOT/tools/alps
export PATH=$ALPS_ROOT/bin:$PATH

#iWaveIC exportup
export IWAVE_ROOT=$PKG_ROOT/$IWAVE_NAME
export IWAVE_HOME=$IWAVE_ROOT/tools/iwave
export PATH=$IWAVE_ROOT/bin:${PATH}

#alpscd exportup
export ALPSCD_ROOT=$PKG_ROOT/$ALPSCD_NAME
export ALPSCD_HOME=$ALPSCD_ROOT/tools/alpscd
export PATH=$ALPSCD_ROOT/bin:$PATH

#rcexplorerIC exportup
export RCEXPLORER_ROOT=$PKG_ROOT/$RCEXPLORER_NAME
export RCEXPLORER_HOME=$RCEXPLORER_ROOT/tools/rcexplorer
export PATH=$RCEXPLORER_ROOT/bin:$PATH

#argusIC exportup
export ARGUS_ROOT=$PKG_ROOT/$ARGUS_NAME
export ARGUS_HOME=$ARGUS_ROOT/tools/argus
export PATH=$ARGUS_ROOT/bin:$PATH

#ADA exportup
export ADA_HOME=$PKG_ROOT/$ADA_NAME
export PATH=$ADA_HOME/bin:$PATH

#Patron exportup
export PATRON_HOME=$PKG_ROOT/$PATRON_NAME
export PATH=$PATRON_HOME/bin:$PATH
export SKI_EMIR_HOME=$PATRON_HOME/tools/skipper_m
export PATH=$SKI_EMIR_HOME/bin:$PATH

#ANDESPM exportup
#export ANACONDA3_INSTALL_PATH=<ANACONDA3_INSTALL_PATH>
#export LUBANPM_HOME=$PKG_ROOT/$ANDESPOWER_NAME
#export PATH=$LUBANPM_HOME/bin:$PATH



#AetherWings
#export AWINGS_HOME='/home/PyAether_Packages/tools/AetherWings_2024.12.tmp3_linux-x86_64_rhel6_20241127/'
#export AWINGS_HOME=$AETHER_ROOT/tools/aetherwings
#export PATH=$AWINGS_HOME/bin:$PATH

