import lvsfunc as lvf
import vapoursynth as vs
from lvsfunc.types import Range
from typing import Tuple, Union, List, Sequence, Optional, Dict, Any
from vsutil import depth as vdepth, get_depth, disallow_variable_format


@disallow_variable_format
def replace_squaremask(
    clipa: vs.VideoNode, clipb: vs.VideoNode, mask_params: Tuple[int, int, int, int],
    ranges: Union[Range, List[Range], None] = None,
    blur_sigma: Optional[int] = None, invert: bool = False
) -> vs.VideoNode:
  import kagefunc as kgf
  assert clipa.format
  assert clipb.format

  mask = kgf.squaremask(clipb, *mask_params)

  if invert:
    mask = mask.std.InvertMask()

  if blur_sigma is not None:
    mask = mask.bilateralgpu.Bilateral(blur_sigma) if clipa.format.bits_per_sample == 32 else mask.bilateral.Gaussian(blur_sigma)

  merge = clipa.std.MaskedMerge(clipb, mask)

  return lvf.rfs(clipa, merge, ranges) if ranges else merge


def freeze_replace_mask(
    mask: vs.VideoNode, insert: vs.VideoNode,
    mask_params: Tuple[int, int, int, int], frame: int, frame_range: Tuple[int, int]
) -> vs.VideoNode:
  masked_insert = replace_squaremask(mask[frame], insert[frame], mask_params)
  return lvf.rfs(mask, masked_insert * mask.num_frames, frame_range)


def depth(*clips_depth: vs.VideoNode, **kwargs: Dict[str, Any]) -> Sequence[vs.VideoNode]:
  assert isinstance(clips_depth[-1], int)

  clips = [vdepth(clip, clips_depth[-1], **kwargs) for clip in clips_depth[:-1]]

  return clips[0] if len(clips) == 1 else clips


@disallow_variable_format
def get_bits(clip: vs.VideoNode, expected_depth: int = 16) -> Tuple[int, vs.VideoNode]:
  return (bits := get_depth(clip)), vdepth(clip, expected_depth) if bits != expected_depth else clip


@disallow_variable_format
def isGray(clip: vs.VideoNode) -> bool:
  assert clip.format
  return clip.format.color_family == vs.GRAY


def checkValue(condition: bool, error_message: str):
  if condition:
    raise ValueError(error_message)


@disallow_variable_format
def checkSimilarClips(clipa: vs.VideoNode, clipb: vs.VideoNode):
  assert clipa.format
  assert clipb.format
  return isinstance(clipa, vs.VideoNode) and isinstance(clipb, vs.VideoNode) and clipa.height == clipb.height and clipa.width == clipb.width and clipa.format.id == clipb.format.id
