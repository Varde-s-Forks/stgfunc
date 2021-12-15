import lvsfunc as lvf
import vapoursynth as vs
from vsutil import insert_clip
from easing_functions import *  # noqa: F401, F403
from easing_functions.easing import EasingBase, LinearInOut

core = vs.core


def fade(clipa: vs.VideoNode, clipb: vs.VideoNode, invert: bool, start: int, end: int, function: EasingBase = LinearInOut):
  clipa_cut = clipa[start:end]
  clipb_cut = clipb[start:end]

  fade = crossfade(*([clipa_cut, clipb_cut] if invert else [clipb_cut, clipa_cut]), function)

  return insert_clip(clipa, fade, start)


def fade_freeze(clipa: vs.VideoNode, clipb: vs.VideoNode, invert: bool, start: int, end: int, function: EasingBase = LinearInOut):
  return fade(
      lvf.rfs(clipa, clipa[start if invert else end] * clipa.num_frames, (start, end)),
      lvf.rfs(clipb, clipb[end if invert else start] * clipb.num_frames, (start, end)),
      invert, start, end, function
  )


def fade_in(clip: vs.VideoNode, start: int, end: int, function: EasingBase = LinearInOut):
  return fade(clip, clip.std.BlankClip(), False, start, end, function)


def fade_out(clip: vs.VideoNode, start: int, end: int, function: EasingBase = LinearInOut):
  return fade(clip, clip.std.BlankClip(), True, start, end, function)


def fade_in_freeze(clip: vs.VideoNode, start: int, end: int, function: EasingBase = LinearInOut):
  return fade_in(lvf.rfs(clip, clip[end] * clip.num_frames, (start, end)), start, end, function)


def fade_out_freeze(clip: vs.VideoNode, start: int, end: int, function: EasingBase = LinearInOut):
  return fade_out(lvf.rfs(clip, clip[start] * clip.num_frames, (start, end)), start, end, function)


def crossfade(clipa: vs.VideoNode, clipb: vs.VideoNode, function: EasingBase, debug: bool = False):
  if clipa.num_frames != clipb.num_frames or clipa.format.id != clipb.format.id or clipa.height != clipb.height or clipa.width != clipb.width:
    raise ValueError('crossfade: Both clips must have the same length, dimensions and format.')

  ease_function = function(0, 1, clipa.num_frames)

  def __fading(n):
    weight = ease_function.ease(n)
    merge = clipa.std.Merge(clipb, weight)
    return merge.text.Text(weight, 9, 2) if debug else merge

  return clipa.std.FrameEval(__fading)
