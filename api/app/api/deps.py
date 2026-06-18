from functools import lru_cache
from typing import Annotated

from fastapi import Depends

from app.core.config import Settings, get_settings
from app.services.generation import Generator, build_generator
from app.services.retrieval import Retriever, build_retriever


@lru_cache
def _retriever_singleton() -> Retriever:
    return build_retriever(get_settings())


@lru_cache
def _generator_singleton() -> Generator:
    return build_generator(get_settings())


def get_retriever() -> Retriever:
    return _retriever_singleton()


def get_generator() -> Generator:
    return _generator_singleton()


SettingsDep = Annotated[Settings, Depends(get_settings)]
RetrieverDep = Annotated[Retriever, Depends(get_retriever)]
GeneratorDep = Annotated[Generator, Depends(get_generator)]
