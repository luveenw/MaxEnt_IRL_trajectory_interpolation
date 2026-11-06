# Maximum Entropy Inverse Reinforcement Learning for Trajectory Interpolation

This repository contains example codes of trajectory interpolation method on the basis of maximum entropy inverse reinforcement learning [1, 2].



## Citation
If you find this code useful, please cite this paper:
* T. Hirakawa, T. Yamashita, T. Tamaki, H. Fujiyoshi, Y. Umezu, I. Takeuchi, S. Matsumoto, K. Yoda, "Can AI predict animal movements? Filling gaps in animal trajectories using Inverse Reinforcement Learning," Ecoshere, vol 9, no. 10, pp. e02447, 2018.



## Requirements
- Language: Python (2.7.\*)
- Modules: Numpy, OpenCV, multiprocessing



## Note
- The program requires a relatively higher performance computer to process in realistic computational time. The training takes approximately 3~4 days with 32 multi-thread processing and 256 GB memory.



## Usage
### Making 3D feature map
> cd data/feature_map \
> python make_3d_feature_map.py 

### Training
> python train.py

### Inference (interpolation)
> python test.py



## Reference
1. T. Hirakawa, T. Yamashita, K. Yoda, T. Tamaki, and H. Fujiyoshi, "Travel Time-dependent Maximum Entropy Inverse Reinforcement Learning for Seabird Trajectory Prediction," in Asian Conference on Computer Vision, pp. 430-435, 2017.
2. T. Hirakawa, T. Yamashita, T. Tamaki, H. Fujiyoshi, Y. Umezu, I. Takeuchi, S. Matsumoto, K. Yoda, "Can AI predict animal movements? Filling gaps in animal trajectories using Inverse Reinforcement Learning," Ecoshere, vol 9, no. 10, pp. e02447, 2018.


## Shared seasonal reward training

See [the seasonal movement architecture and operating manual](jaguar_irl/training/README_SHARED.md)
for the full workflow: source/missingness audit, bout selection, spatial groups,
identity-preserving exports, covariate preparation, joint training and atomic
resumption. Scientific testing has an explicit placeholder pending review.
[Architecture decision](docs/adr/0001-seasonal-joint-reward.md) and
[glossary](GLOSSARY.md) provide the rationale and terminology. The root
[AGENTS.md](AGENTS.md) requires updates to the manual with workflow changes.

Training entry point: `python3 -m jaguar_irl.training.shared --help`.
