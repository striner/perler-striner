from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any

from python_backend.algorithms.errors import InvalidRequestError

from .types import Detection


@dataclass(frozen=True, slots=True)
class TokenObject:
    object_id: str
    box: tuple[float, float, float, float]
    score: float
    type_id: int
    type_name_en: str
    salience: float


class AnalysisTokenSigner:
    def __init__(self, secret: str, ttl_seconds: int) -> None:
        if not secret:
            raise ValueError("analysis token secret must not be empty")
        self._secret = secret.encode("utf-8")
        self._ttl_seconds = ttl_seconds

    def issue(
        self,
        image_data: bytes,
        detections: list[Detection],
        image_width: int,
        image_height: int,
    ) -> tuple[str, list[TokenObject]]:
        objects = [
            TokenObject(
                object_id=f"object_{index + 1}",
                box=tuple(round(value, 8) for value in detection.box),
                score=detection.score,
                type_id=detection.type_id,
                type_name_en=detection.type_name_en,
                salience=detection.salience,
            )
            for index, detection in enumerate(detections)
        ]
        payload = {
            "v": 1,
            "alg": "tiny_model",
            "alg_ver": "1.0.0",
            "exp": int(time.time()) + self._ttl_seconds,
            "sha256": hashlib.sha256(image_data).hexdigest(),
            "image": [image_width, image_height],
            "objects": [
                {
                    "id": item.object_id,
                    "box": item.box,
                    "score": round(item.score, 8),
                    "type_id": item.type_id,
                    "en": item.type_name_en,
                    "salience": round(item.salience, 8),
                }
                for item in objects
            ],
        }
        encoded = _encode_json(payload)
        signature = hmac.new(self._secret, encoded.encode("ascii"), hashlib.sha256).digest()
        return f"{encoded}.{_base64url(signature)}", objects

    def verify(self, token: str, image_data: bytes) -> list[TokenObject]:
        try:
            encoded, supplied_signature = token.split(".", 1)
            expected = hmac.new(
                self._secret,
                encoded.encode("ascii"),
                hashlib.sha256,
            ).digest()
            if not hmac.compare_digest(_decode_base64url(supplied_signature), expected):
                raise ValueError("signature mismatch")
            payload = json.loads(_decode_base64url(encoded))
            return self._validate_payload(payload, image_data)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise InvalidRequestError("analysis token is invalid") from error

    def _validate_payload(self, payload: Any, image_data: bytes) -> list[TokenObject]:
        if not isinstance(payload, dict):
            raise ValueError("payload is not an object")
        if payload.get("v") != 1 or payload.get("alg") != "tiny_model":
            raise ValueError("token contract mismatch")
        if payload.get("alg_ver") != "1.0.0":
            raise ValueError("algorithm version mismatch")
        if not isinstance(payload.get("exp"), int) or payload["exp"] < int(time.time()):
            raise ValueError("token expired")
        if payload.get("sha256") != hashlib.sha256(image_data).hexdigest():
            raise ValueError("image digest mismatch")
        raw_objects = payload.get("objects")
        if not isinstance(raw_objects, list) or not 1 <= len(raw_objects) <= 24:
            raise ValueError("invalid object list")
        objects = []
        for raw in raw_objects:
            if not isinstance(raw, dict):
                raise ValueError("invalid object")
            box = raw.get("box")
            if (
                not isinstance(box, list)
                or len(box) != 4
                or any(
                    isinstance(value, bool) or not isinstance(value, (int, float)) for value in box
                )
            ):
                raise ValueError("invalid object box")
            normalized = tuple(float(value) for value in box)
            if not all(0 <= value <= 1 for value in normalized):
                raise ValueError("object box is out of range")
            objects.append(
                TokenObject(
                    object_id=_text(raw.get("id")),
                    box=normalized,
                    score=_number(raw.get("score")),
                    type_id=_integer(raw.get("type_id")),
                    type_name_en=_text(raw.get("en")),
                    salience=_number(raw.get("salience")),
                )
            )
        if len({item.object_id for item in objects}) != len(objects):
            raise ValueError("duplicate object id")
        return objects


def _encode_json(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return _base64url(raw)


def _base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _decode_base64url(value: str) -> bytes:
    if not value or len(value) > 32_768:
        raise ValueError("invalid base64url")
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def _text(value: Any) -> str:
    if not isinstance(value, str) or not value or len(value) > 128:
        raise ValueError("invalid text")
    return value


def _number(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("invalid number")
    result = float(value)
    if not 0 <= result <= 1:
        raise ValueError("number is out of range")
    return result


def _integer(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("invalid integer")
    return value
