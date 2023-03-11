from meerkat import env
from meerkat.tools.lazy_loader import LazyLoader
from meerkat.tools.utils import requires

torch = LazyLoader("torch")
torchaudio = LazyLoader("torchaudio")


class Audio:
    def __init__(
        self,
        data,
        sampling_rate: int,
        bits: int = None,
    ) -> None:
        if not env.is_package_installed("torch"):
            raise ValueError(
                f"{type(self)} requires torch. Follow these instructions "
                "to install torch: https://pytorch.org/get-started/locally/."
            )
        self.data = torch.as_tensor(data)
        self.sampling_rate = sampling_rate
        self.bits = bits

    def duration(self) -> float:
        """Return the duration of the audio in seconds."""
        return len(self.data) / self.sampling_rate

    @requires("torchaudio")
    def resample(self, sampling_rate: int) -> "Audio":
        """Resample the audio with a new sampling rate.

        Args:
            sampling_rate: The new sampling rate.

        Returns:
            The resampled audio.
        """
        if not env.is_package_installed("torchaudio"):
            raise ValueError(
                "resample requires torchaudio. Install with `pip install torchaudio`."
            )

        return Audio(
            torchaudio.functional.resample(
                self.data, self.sampling_rate, sampling_rate
            ),
            sampling_rate,
        )

    def quantize(self, bits: int, epsilon: float = 1e-2) -> "Audio":
        """Linearly quantize a signal to a given number of bits.

        The signal must be in the range [0, 1].

        Args:
            bits: The number of bits to quantize to.
            epsilon: The epsilon to use for clipping the signal.

        Returns:
            The quantized audio.
        """
        if self.bits is not None:
            raise ValueError("Audio is already quantized. Cannot quantize again.")

        q_levels = 1 << bits
        samples = (q_levels - epsilon) * self.data
        samples += epsilon / 2
        return Audio(samples, sampling_rate=self.sampling_rate, bits=self.bits)

    def __repr__(self) -> str:
        return f"Audio({self.duration()} seconds @ {self.sampling_rate}Hz)"

    def __eq__(self, other: "Audio") -> bool:
        return (
            self.data.shape == other.data.shape
            and self.sampling_rate == other.sampling_rate
            and torch.allclose(self.data, other.data)
        )

    def __getitem__(self, key: int) -> "Audio":
        return Audio(self.data[key], self.sampling_rate)

    def __len__(self) -> int:
        return len(self.data)

    def _repr_html_(self) -> str:
        import IPython.display as ipd

        return ipd.Audio(self.data, rate=self.sampling_rate)._repr_html_()
