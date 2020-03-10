@echo off
call conda activate barotse
echo "Installing Wflow..."
pip install git+https://github.com/openstreams/wflow.git
