conda create -n image-extractor-test python=3.10 pip -y
conda activate image-extractor-test
conda install -y requests beautifulsoup4 tqdm ipykernel
conda install -y pdf2image poppler opencv
conda install -y pytorch torchvision cpuonly -c pytorch
pip install layoutparser ipywidgets