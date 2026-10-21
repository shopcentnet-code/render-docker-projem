import os
import tempfile

import spaces  # ZeroGPU: torch'tan ONCE import edilmeli!

import gradio as gr
import numpy as np
import soundfile as sf
import torch

from demucs.pretrained import get_model
from demucs.apply import apply_model

# Model aciliste bir kez yuklenir (ZeroGPU Space'te CPU'da bekler, islem GPU'da yapilir)
MODEL = get_model("htdemucs")
MODEL.eval()


def load_audio(path):
    data, sr = sf.read(path, dtype="float32", always_2d=True)  # [T, C]
    wav = torch.from_numpy(data.T)  # [C, T]
    if wav.shape[0] == 1:
        wav = torch.cat([wav, wav], dim=0)  # mono -> stereo
    return wav, sr


@spaces.GPU(duration=55)
def separate(audio_file):
    if audio_file is None:
        raise gr.Error("Lutfen bir muzik / ses dosyasi secin!")

    wav, sr = load_audio(audio_file)
    ref = wav.mean(0)
    wav = (wav - ref.mean()) / (ref.std() + 1e-8)

    model = MODEL.to("cuda")
    with torch.no_grad():
        stems = apply_model(
            model,
            wav[None].to("cuda"),
            device="cuda",
            split=True,
            overlap=0.25,
            progress=False,
        )[0]

    stems = stems.cpu() * (ref.std() + 1e-8) + ref.mean()

    vocals_idx = model.sources.index("vocals")
    vocals = stems[vocals_idx]
    instrumental = stems.sum(dim=0) - vocals

    out_dir = tempfile.mkdtemp()
    vocals_path = os.path.join(out_dir, "vocals.wav")
    inst_path = os.path.join(out_dir, "instrumental.wav")

    sf.write(vocals_path, vocals.T.numpy(), sr)
    sf.write(inst_path, instrumental.T.numpy(), sr)

    return vocals_path, inst_path


with gr.Blocks(title="SAZKOMANDO Vokal Ayirici") as demo:
    gr.Markdown(
        """
        # 🎙️ SAZKOMANDO AI Vokal Ayrıcı
        Şarkıdan **vokal** ve **enstrümantal** parçayı ayırır (Meta Demucs AI).
        Mikrofon simgesine basılıp PC'den dosya seçilebilir; ya da kaydedilir.
        """
    )
    with gr.Row():
        audio_in = gr.Audio(
            sources=["upload", "microphone"],
            type="filepath",
            label="Müzik / Ses Dosyası (MP3, WAV)",
        )
    with gr.Row():
        btn = gr.Button("🚀 Sesi ve Vokali Ayır", variant="primary", scale=1)
    with gr.Row():
        gr.Markdown("İşlem ilk seferde model indirmesi nedeniyle biraz sürebilir…")
    with gr.Row():
        vocals_out = gr.Audio(label="🎤 Vokal (Sadece Ses)")
        inst_out = gr.Audio(label="🎸 Enstrümantal (Müzik)")

    btn.click(separate, inputs=audio_in, outputs=[vocals_out, inst_out])


if __name__ == "__main__":
    demo.launch()
