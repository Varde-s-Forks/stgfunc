from __future__ import annotations

import enum
import os
import random
import subprocess
from pathlib import Path
from typing import BinaryIO, Callable, Concatenate, Dict, List, NamedTuple, ParamSpec, cast

import vapoursynth as vs
from lvsfunc.progress import BarColumn, FPSColumn, Progress, TextColumn, TimeRemainingColumn
from lvsfunc.render import clip_async_render

core = vs.core
# Mostly code and base idea from LightArrowsEXE and Vardë,
# rewrote a bunch of it and put everything into a handy class


PROPS_LR = {
    '_Matrix': 6,
    '_Transfer': 6,
    '_Primaries': 6,
    '_FieldBased': 0,
    '_ChromaLocation': 0
}
PROPS_HR = {
    '_Matrix': 1,
    '_Transfer': 1,
    '_Primaries': 1
}


class ResType(str, enum.Enum):
    LR = 'LR'
    HR = 'HR'


class DatasetClip(NamedTuple):
    clip: vs.VideoNode
    res_type: ResType


class Datasets(NamedTuple):
    hr: DatasetClip
    lr: DatasetClip


P = ParamSpec('P')


def ensure_ffmpeg_GBR(func: Callable[Concatenate[PrepareDataset, P], vs.VideoNode]) -> Callable[Concatenate[PrepareDataset, P], vs.VideoNode]:
    def _to_BGR(self: PrepareDataset, *args: P.args, **kwargs: P.kwargs) -> vs.VideoNode:
        clip = func(self, *args, **kwargs)
        return_gbr = self.trainer.is_train
        rgb = clip.resize.Bicubic(format=vs.RGB24, dither_type='error_diffusion')
        return rgb.std.ShufflePlanes([1, 2, 0], vs.RGB) if return_gbr else rgb
    return _to_BGR


def join_clips(clips: List[vs.VideoNode]) -> vs.VideoNode:
    full = core.std.BlankClip(clips[0][0])

    for c in clips:
        full += c

    return full[1:]


class PrepareDataset:
    def __init__(self, trainer: TraiNNing) -> None:
        self.trainer = trainer

    def prepare_training(self) -> Datasets:
        if not self.trainer.is_train:
            raise RuntimeError('You need to set is_train to True!')

        print('Checking clips lengths...')
        if (length := self.trainer.hr_clip.num_frames) == self.trainer.lr_clip.num_frames:
            frames = sorted(random.sample(
                population=range(length), k=round(length / 2)))
        else:
            raise IndexError("LR and HR aren't the same length!")

        print('Creating folders...')
        for path in [self.trainer.path_dataset_train, self.trainer.path_dataset_val]:
            if not path.exists():
                path.mkdir(parents=True, exist_ok=True)

        print('Preparing the filtered LR and HR clips...')
        prep_lr = self.prepare_lr(self.trainer.lr_clip)
        prep_hr = self.prepare_hr(self.trainer.hr_clip, self.trainer.lr_clip)

        print('Splicing LR and HR clips...')
        lr = core.std.Splice([prep_lr[f] for f in frames])
        hr = core.std.Splice([prep_hr[f] for f in frames])

        return Datasets(DatasetClip(hr, ResType.HR), DatasetClip(lr, ResType.LR))

    @ensure_ffmpeg_GBR
    def prepare_hr(self) -> vs.VideoNode:
        raise NotImplementedError('Function not implemented!')

    @ensure_ffmpeg_GBR
    def prepare_lr(self) -> vs.VideoNode:
        raise NotImplementedError('Function not implemented!')


class ExportDataset:
    def __init__(self, basicSR: TraiNNing) -> None:
        self.trainer = basicSR

        def write_image_async(self, dataset: Datasets) -> None:
            print('Extracting LR...')
            self._output_images(dataset.lr)
            print('Extracting HR...')
            self._output_images(dataset.hr)

    def _output_images(self, clip_dts: DatasetClip) -> None:
        if not (path := self.trainer.path_dataset_train.joinpath(clip_dts.res_type)).exists():
            path.mkdir(parents=True)

        progress = Progress(
            TextColumn('{task.description}'),
            BarColumn(),
            TextColumn('{task.completed}/{task.total}'),
            TextColumn('{task.percentage:>3.02f}%'),
            FPSColumn(),
            TimeRemainingColumn()
        )

        with progress:
            task = progress.add_task(
                'Extracting frames...', total=clip_dts.clip.num_frames)

            def _cb(n: int, f: vs.VideoFrame) -> None:
                progress.update(task, advance=1)

            clip = clip_dts.clip.imwri.Write(
                'PNG', filename=str(path.joinpath('%06d.png'))
            )

            clip_async_render(clip, progress=None, callback=_cb)

    def write_video(self, dataset: Datasets) -> None:
        print('Encoding and extracting LR...')
        self._encode_and_extract(dataset.lr)
        print('Encoding and extracting HR...')
        self._encode_and_extract(dataset.hr)

    def _encode_and_extract(self, clip_dts: DatasetClip) -> None:
        if not (path := self.trainer.path_dataset_train.joinpath(clip_dts.res_type)).exists():
            path.mkdir(parents=True)

        params = [
            'ffmpeg', '-hide_banner', '-f', 'rawvideo',
            '-video_size', f'{str(clip_dts.clip.width)}x{str(clip_dts.clip.height)}',
            '-pixel_format', 'gbrp', '-framerate', str(clip_dts.clip.fps),
            '-i', 'pipe:', str(path.joinpath('%06d.png'))
        ]

        print('Encoding...\n')
        with subprocess.Popen(params, stdin=subprocess.PIPE) as process:
            clip_dts.clip.output(cast(BinaryIO, process.stdin))

    def select_val_images(self, dataset: Datasets, number: int) -> None:
        if not (path_val_hr := self.trainer.path_dataset_val.joinpath(dataset.hr.res_type)).exists():
            path_val_hr.mkdir(parents=True)
        if not (path_val_lr := self.trainer.path_dataset_val.joinpath(dataset.lr.res_type)).exists():
            path_val_lr.mkdir(parents=True)

        if not (path_train_hr := self.trainer.path_dataset_train.joinpath(dataset.hr.res_type)).exists():
            raise FileNotFoundError(f'{path_train_hr} not found')
        if not (path_train_lr := self.trainer.path_dataset_train.joinpath(dataset.lr.res_type)).exists():
            raise FileNotFoundError(f'{path_train_lr} not found')

        images_path = sorted(path_train_hr.glob('*.png'))
        image_idx = random.sample(population=range(len(images_path)), k=number)

        for i in image_idx:
            name = images_path[i].name
            os.system(
                f'copy "{path_train_hr.joinpath(name)}" "{path_val_hr.joinpath(name)}"')
            os.system(
                f'copy "{path_train_lr.joinpath(name)}" "{path_val_lr.joinpath(name)}"')


class TraiNNing:
    _lr_clip: vs.VideoNode
    _hr_clip: vs.VideoNode

    path_dataset_train: Path
    path_dataset_val: Path

    def __init__(
        self, lr_clip: vs.VideoNode, hr_clip: vs.VideoNode,
        dataset_path: Path, is_train: bool = True,
        props_lr: Dict[str, int] = PROPS_LR,
        props_hr: Dict[str, int] = PROPS_HR,
    ):
        self.props_lr = props_lr
        self.props_hr = props_hr
        self.is_train = is_train

        self.lr_clip = lr_clip
        self.hr_clip = hr_clip

        self.path_dataset_train = dataset_path.joinpath('train')
        self.path_dataset_val = dataset_path.joinpath('val')

    @property
    def lr_clip(self):
        return self._lr_clip

    @lr_clip.setter
    def lr_clip(self, new_clip):
        self._lr_clip = new_clip.std.SetFrameProps(**self.props_lr)

    @property
    def hr_clip(self):
        return self._hr_clip

    @hr_clip.setter
    def hr_clip(self, new_clip):
        self._hr_clip = new_clip.std.SetFrameProps(**self.props_hr)

    def get_prepare_dataset(self) -> PrepareDataset:
        return PrepareDataset(self)

    def get_export_dataset(self) -> ExportDataset:
        return ExportDataset(self)
