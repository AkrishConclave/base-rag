from setuptools import Extension, setup


setup(
    name="base-rag-vector-native",
    version="0.1.0",
    description="Native CPU vector search for Base RAG",
    ext_modules=[
        Extension(
            "rag_vector_native",
            sources=["native/vector_search.c"],
            extra_compile_args=["-O3"],
        )
    ],
)
