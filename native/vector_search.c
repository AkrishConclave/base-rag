#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <math.h>
#include <stdint.h>
#include <stdlib.h>

#if (defined(__x86_64__) || defined(__i386__)) && (defined(__clang__) || defined(__GNUC__))
#include <immintrin.h>
#define HAVE_X86_AVX2_DISPATCH 1
#endif

#if defined(__aarch64__) || defined(__ARM_NEON)
#include <arm_neon.h>
#define HAVE_ARM_NEON 1
#endif

/*
 * Exact cosine top-K for already L2-normalised float32 vectors.
 * The matrix is row-major and contiguous: [count][dimension].  Python/Numpy
 * owns the memory, so this function never copies the embedding corpus.
 */
typedef struct {
    float score;
    int64_t index;
} Hit;

static void sift_down(Hit *heap, Py_ssize_t size, Py_ssize_t root) {
    while (1) {
        Py_ssize_t child = root * 2 + 1;
        if (child >= size) return;
        if (child + 1 < size && heap[child + 1].score < heap[child].score) child++;
        if (heap[root].score <= heap[child].score) return;
        Hit value = heap[root]; heap[root] = heap[child]; heap[child] = value;
        root = child;
    }
}

static void sift_up(Hit *heap, Py_ssize_t index) {
    while (index > 0) {
        Py_ssize_t parent = (index - 1) / 2;
        if (heap[parent].score <= heap[index].score) return;
        Hit value = heap[parent]; heap[parent] = heap[index]; heap[index] = value;
        index = parent;
    }
}

static int compare_desc(const void *left, const void *right) {
    const Hit *a = (const Hit *)left;
    const Hit *b = (const Hit *)right;
    return (a->score < b->score) - (a->score > b->score);
}

static float dot_product_scalar(const float *left, const float *right, Py_ssize_t dimension) {
    float sum0 = 0.0f, sum1 = 0.0f, sum2 = 0.0f, sum3 = 0.0f;
    Py_ssize_t i = 0;
    /* Four independent accumulators help Clang/GCC auto-vectorise to AVX/NEON. */
    for (; i + 3 < dimension; i += 4) {
        sum0 += left[i] * right[i];
        sum1 += left[i + 1] * right[i + 1];
        sum2 += left[i + 2] * right[i + 2];
        sum3 += left[i + 3] * right[i + 3];
    }
    float sum = (sum0 + sum1) + (sum2 + sum3);
    for (; i < dimension; i++) sum += left[i] * right[i];
    return sum;
}

#ifdef HAVE_X86_AVX2_DISPATCH
__attribute__((target("avx2,fma")))
static float dot_product_avx2(const float *left, const float *right, Py_ssize_t dimension) {
    __m256 sum = _mm256_setzero_ps();
    Py_ssize_t i = 0;
    for (; i + 7 < dimension; i += 8) {
        sum = _mm256_fmadd_ps(_mm256_loadu_ps(left + i), _mm256_loadu_ps(right + i), sum);
    }
    float lanes[8];
    _mm256_storeu_ps(lanes, sum);
    float result = lanes[0] + lanes[1] + lanes[2] + lanes[3] + lanes[4] + lanes[5] + lanes[6] + lanes[7];
    for (; i < dimension; i++) result += left[i] * right[i];
    return result;
}
#endif

#ifdef HAVE_ARM_NEON
static float dot_product_neon(const float *left, const float *right, Py_ssize_t dimension) {
    float32x4_t sum = vdupq_n_f32(0.0f);
    Py_ssize_t i = 0;
    for (; i + 3 < dimension; i += 4) {
        sum = vmlaq_f32(sum, vld1q_f32(left + i), vld1q_f32(right + i));
    }
    float result = vaddvq_f32(sum);
    for (; i < dimension; i++) result += left[i] * right[i];
    return result;
}
#endif

static float dot_product(const float *left, const float *right, Py_ssize_t dimension) {
#ifdef HAVE_X86_AVX2_DISPATCH
    if (__builtin_cpu_supports("avx2") && __builtin_cpu_supports("fma")) {
        return dot_product_avx2(left, right, dimension);
    }
#endif
#ifdef HAVE_ARM_NEON
    return dot_product_neon(left, right, dimension);
#else
    return dot_product_scalar(left, right, dimension);
#endif
}

static PyObject *cosine_top_k(PyObject *self, PyObject *args) {
    Py_buffer matrix = {0}, query = {0}, candidates = {0};
    Py_ssize_t rows, dimension, top_k;
    if (!PyArg_ParseTuple(args, "y*y*nnny*", &matrix, &query, &rows, &dimension, &top_k, &candidates)) {
        return NULL;
    }
    if (rows < 0 || dimension <= 0 || top_k <= 0 || matrix.len != rows * dimension * (Py_ssize_t)sizeof(float)
        || query.len != dimension * (Py_ssize_t)sizeof(float) || candidates.len % (Py_ssize_t)sizeof(int64_t) != 0) {
        PyBuffer_Release(&matrix); PyBuffer_Release(&query); PyBuffer_Release(&candidates);
        PyErr_SetString(PyExc_ValueError, "invalid contiguous float32 matrix, query, or int64 candidates");
        return NULL;
    }

    const float *vectors = (const float *)matrix.buf;
    const float *query_vector = (const float *)query.buf;
    const int64_t *candidate_indices = (const int64_t *)candidates.buf;
    Py_ssize_t candidate_count = candidates.len / (Py_ssize_t)sizeof(int64_t);
    if (top_k > candidate_count) top_k = candidate_count;
    Hit *heap = top_k ? PyMem_Malloc((size_t)top_k * sizeof(Hit)) : NULL;
    if (top_k && !heap) {
        PyBuffer_Release(&matrix); PyBuffer_Release(&query); PyBuffer_Release(&candidates);
        return PyErr_NoMemory();
    }

    Py_ssize_t heap_size = 0;
    Py_BEGIN_ALLOW_THREADS
    for (Py_ssize_t candidate = 0; candidate < candidate_count; candidate++) {
        int64_t index = candidate_indices[candidate];
        if (index < 0 || index >= rows) continue;
        float score = dot_product(vectors + index * dimension, query_vector, dimension);
        if (heap_size < top_k) {
            heap[heap_size] = (Hit){score, index};
            sift_up(heap, heap_size++);
        } else if (top_k && score > heap[0].score) {
            heap[0] = (Hit){score, index};
            sift_down(heap, heap_size, 0);
        }
    }
    if (heap_size > 1) qsort(heap, (size_t)heap_size, sizeof(Hit), compare_desc);
    Py_END_ALLOW_THREADS

    PyObject *result = PyList_New(heap_size);
    if (result) {
        for (Py_ssize_t i = 0; i < heap_size; i++) {
            PyObject *item = Py_BuildValue("Ld", (long long)heap[i].index, (double)heap[i].score);
            if (!item) { Py_DECREF(result); result = NULL; break; }
            PyList_SET_ITEM(result, i, item);
        }
    }
    PyMem_Free(heap);
    PyBuffer_Release(&matrix); PyBuffer_Release(&query); PyBuffer_Release(&candidates);
    return result;
}

static PyMethodDef methods[] = {
    {"cosine_top_k", cosine_top_k, METH_VARARGS, "Exact cosine top-K over a float32 matrix."},
    {NULL, NULL, 0, NULL},
};

static struct PyModuleDef module = {PyModuleDef_HEAD_INIT, "rag_vector_native", NULL, -1, methods};
PyMODINIT_FUNC PyInit_rag_vector_native(void) { return PyModule_Create(&module); }
