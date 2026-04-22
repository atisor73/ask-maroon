conda env create -f img_extractor.yml
conda activate image-extractor
python -m pip install --no-build-isolation 'git+https://github.com/facebookresearch/detectron2.git'

# Download NewspaperNavigator model weights directly (LayoutParser wrapper is mothballed)
mkdir -p ~/newspaper_navigator_model
wget -O ~/newspaper_navigator_model/model_final.pth \
  "https://github.com/LibraryOfCongress/newspaper-navigator/releases/download/v1.0.0/model_final.pth"