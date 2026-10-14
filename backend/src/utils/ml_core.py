import open_clip
import torch
from PIL import Image
from utils.config import CLIP_MODEL_NAME

model, preprocess, tokenizer = None, None, None


def load_model():
    global model, preprocess, tokenizer
    if model is None or preprocess is None or tokenizer is None:
        model, _, preprocess = open_clip.create_model_and_transforms(CLIP_MODEL_NAME)
        tokenizer = open_clip.get_tokenizer(CLIP_MODEL_NAME)
        model.eval()
    return model, preprocess, tokenizer


def get_image_embedding(image_path: str) -> list[float]:
    model, preprocess, _ = load_model()
    image = Image.open(image_path).convert("RGB")
    image_tensor = preprocess(image).unsqueeze(0)  # type: ignore

    with (
        torch.no_grad(),
        torch.amp.autocast("cuda" if torch.cuda.is_available() else "cpu"),
    ):
        features = model.encode_image(image_tensor, normalize=True)  # type: ignore
    return features.squeeze(0).tolist()


def get_text_embedding(text_query: str) -> list[float]:
    model, _, tokenizer = load_model()
    text_tokens = tokenizer([text_query], context_length=model.context_length)  # type: ignore

    with (
        torch.no_grad(),
        torch.amp.autocast("cuda" if torch.cuda.is_available() else "cpu"),
    ):
        features = model.encode_text(text_tokens, normalize=True)  # type: ignore
    return features.squeeze(0).tolist()
