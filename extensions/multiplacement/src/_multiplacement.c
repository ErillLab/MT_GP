#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdbool.h>
#include <limits.h>
#include "_constants.h"
const int NUM_BASES = 4;

int min(int n, int k){
  if (n > k)
    return k;
  else
    return n;
}

unsigned long long bin(unsigned long long n, unsigned long long k){

  unsigned long long c = 1;
  for (unsigned long long i = 1; i <= k; i++, n--) {

    if (c/i > ULONG_MAX/n) // return 0 on potential overflow
      return 0;

    c = c / i * n + c % i * n / i; // split c * n / i into (c / i * i + c % i) * n / i
  }

  return c; 
}

float norm_cdf(float x, float mu, float sigma){
  float z = (x - mu) / fabs(sigma);
  return (1 + erff(z / sqrtf(2.0))) / 2.00;
}

float norm_pf(float x, float mu, float sigma){
  if (sigma != 0)
    return norm_cdf(x + 0.5, mu, sigma) - norm_cdf(x - 0.5, mu, sigma);
  if (x == mu)
    return 1.00;
  return 0.00;
}

float get_numerator(int dna_length, int distance, float mu, float sigma){
  float numerator = norm_pf(distance, mu, sigma);
  if (sigma == 0.00)
    return numerator;

  float auc = norm_cdf(dna_length - 1, mu, sigma) - norm_cdf(0, mu, sigma);
  if (auc < 0.000001)
    auc = 0.000001;

  if (numerator < 0.00001)
    numerator = 0.00001;

  return numerator /= auc;

}

float get_denominator(int d, int N, int L){
  if (1 <= d && d <= L - N + 1)
    return (float) bin(L - d, N - 1) / (float) bin(L, N);
  return 0.0001;
}

float get_score(float *arr, int dna_length, int effective_length, int num_rec, 
                int gap_size, int max_length, int curr_conn, bool is_precomputed){
  if (is_precomputed == false){
    return log2f(get_numerator(dna_length, gap_size, arr[curr_conn * 2], arr[curr_conn * 2 + 1]) / 
                 get_denominator(gap_size + 1, num_rec, effective_length));
  }
  
  return log2(arr[curr_conn * max_length + gap_size]) - 
          (
            (
              NUMERATORS[(effective_length - (gap_size + 1)) - 1] - 
              NUMERATORS[(num_rec - 1) - 1] - 
              NUMERATORS[effective_length - (gap_size + 1) - (num_rec - 1) - 1]
            ) -

            (
              NUMERATORS[effective_length - 1] - 
              NUMERATORS[num_rec - 1] - 
              NUMERATORS[effective_length - num_rec - 1]
            )
          );
}

int get_forward_offset(int index, int cols[], int num_rec) {
  // finds the first possible possition for a pssm
  // based on number of columns of preceding pssms

  int offset = 0;
  for (int i = 0; i < index; i++) {
    offset += cols[i];
  }
  return offset;
}

int get_reverse_offset(int index, int cols[], int num_rec) {
  // finds the last possible possition for a pssm
  // based on number of columns of subsequenct pssms

  int offset = 0;
  for (int i = num_rec - 1; i >= index; i--) {
    offset += cols[i];
  }

  // this is important to get the right number of possible alignments
  return offset - 1;
}

int max_index(float *arr, int size) {
  int max_index = 0;
  for (int i = 0; i < size; i++) {

    if (arr[i] > arr[max_index]) {
      max_index = i;
    }
  }
  return max_index;
}

void traceback(int num_rec, int len_seq, float* con_matrices, float* rec_score_matrix, 
               int num_alignments, float* rec_alignments, int* con_alignments,
               float* rec_scores, float* con_scores, int* con_lengths, int max_seq_len, int effective_len, bool is_precomputed){
  // finding gap lengths to ref orma alignments
  // starting from the index of the greatest score in alignments
  // trace back of gap alignments is conducted by subtracting the value
  // at the max score index from the index and going up a row
  // this is repeated until we know all the gap lengths in the alignment
  int index = max_index(rec_alignments, num_alignments);
  con_lengths[num_rec - 1] = con_alignments[(num_rec - 2) * num_alignments + index];

  // the cumulative best score is written into the last index of the scores
  // array
  rec_scores[num_rec] = rec_alignments[index];

  //the start and end of this for loop are weird because the first and last
  //indices are filled manually, so these bounds only encompass the middle
  //scores
  for (int i = num_rec - 3; i >= 0; i--) {
    con_lengths[i + 1] = con_alignments[i * num_alignments + index - con_lengths[i + 2]];
    index -= con_lengths[i + 2];
  }
  con_lengths[0] = index - con_lengths[1];

  int gapOffset = 0;
  for (int i = 0; i < num_rec - 1; i++) {
    //con_scores[i] = get_score(con_matrices[i * max_seq_len + con_lengths[i + 1]], effective_len, num_rec, con_lengths[i + 1]);
    con_scores[i] = get_score(con_matrices, len_seq, effective_len, num_rec, con_lengths[i + 1], max_seq_len, i, is_precomputed);
  }

  // scores for each PSSM are filled by iterating over the score matrix
  // and using the appropriate gap lengths as a cumulative offset
  for (int i = 0; i < num_rec; i++) {
    gapOffset += con_lengths[i];
    rec_scores[i] = rec_score_matrix[i * num_alignments + gapOffset];
  }

}

void fill_traceback_matrix(float *score_matrix, int num_alignments, float *gapMatrix,
                           int *cols, int num_rec, int len_seq, float *con_scores, float *rec_scores, 
                           int *con_lengths, int max_length, bool is_precomputed) {
  int gap_length = 0;
  int effective_length = len_seq;
  int sum_of_lengths = 0;

  for (int i = 0; i < num_rec; i++){
    sum_of_lengths += cols[i];
  }

  effective_length -= sum_of_lengths;
  //  number of total alignments by number of pssms
  //  first index in each column holds current max score for that index
  //  all other indices hold gap lengths that got that alignment
  float *alignments = PyMem_Calloc(num_alignments, sizeof(*score_matrix));
  int *gap_alignments = PyMem_Calloc(num_alignments * (num_rec - 1), sizeof(*con_lengths));
  float *temp_max_scores = PyMem_Calloc(num_alignments, sizeof(*score_matrix));
  int *temp_gap_lengths = PyMem_Calloc(num_alignments, sizeof(*con_lengths));
  float temp_gap_score = 0.0;

  // start with first row as our current max
  for (int i = 0; i < num_alignments; i++) {
    alignments[i] = score_matrix[i];
    temp_max_scores[i] = score_matrix[i];
  }

  // for each connector (number of pssms - 1) populate alignments with
  // current maximum score for that index

  // overview: the algorithm iterates over the next row in the scoresMatrix
  // (first row is our starting cumulative score), for each index, we compare
  // the scores obtained by summing the PSSM score at that index with each
  // previous cumulative alignment score for k <= j, when k == j, the gap length
  // is 0
  for (int i = 1; i < num_rec; i++) {

    for (int j = 0; j < num_alignments; j++) {

      for (int k = 0; k <= j; k++) {

        // every column before or equal to the current column is a valid
        // alignment. Scores for each alignment
        // gap_length = difference between column normalized j and k
        gap_length = j - k;

        //compute on fly
        //temp_gap_score = get_score(gapMatrix[(i - 1) * max_length + gap_length], effective_length, num_rec, gap_length);
        temp_gap_score = get_score(gapMatrix, len_seq, effective_length, num_rec, gap_length, max_length, i - 1, is_precomputed);
        if (k == 0) {
          temp_max_scores[j] = alignments[k] +
                               temp_gap_score +
                               score_matrix[i * num_alignments + j];
          temp_gap_lengths[j] = gap_length;
        }else{
          if (temp_max_scores[j] < alignments[k] + temp_gap_score + score_matrix[i * num_alignments + j]) {
              temp_max_scores[j] = alignments[k] + temp_gap_score + score_matrix[i * num_alignments + j];
              temp_gap_lengths[j] = gap_length;
          }
        }
      }
    }

    // we must reset our temp arrays so that they will be overwritten
    // when doing the comparison of scores
    for (int l = 0; l < num_alignments; l++) {
      alignments[l] = temp_max_scores[l];
      gap_alignments[(i - 1) * num_alignments + l] = temp_gap_lengths[l];
      temp_max_scores[l] = -INFINITY;
      temp_gap_lengths[l] = 0;
    }
  }
  PyMem_Free(temp_max_scores);
  PyMem_Free(temp_gap_lengths);

  traceback(num_rec, len_seq, gapMatrix, score_matrix, 
            num_alignments, alignments, gap_alignments,
            rec_scores, con_scores, con_lengths, max_length, 
            effective_length, is_precomputed);

  PyMem_Free(alignments);
  PyMem_Free(gap_alignments);
  
}

void fill_matrix(const char seq[], int len_seq, float pssm[], int cols[],
                 int num_rec, float score_matrix[], int num_alignments) {
  // length of the seq by number of pssms

  // printf("last in fill_matrix\n");
  float score = 0;
  int forward_offset = 0;
  int reverse_offset = 0;

  // pre computes alignments of each pssm at each possible position
  // i = current recognizer
  // j = starting position on seq for computing score
  // k = current column in recognizer

  for (int i = 0; i < num_rec; i++) {
    forward_offset = get_forward_offset(i, cols, num_rec);
    reverse_offset = get_reverse_offset(i, cols, num_rec);

    for (int j = forward_offset; j < len_seq - reverse_offset; j++) {
      score = 0;
      for (int k = 0; k < cols[i]; k++) {
        switch (seq[j + k]) {
        case 'A':
        case 'a':
          score += pssm[(forward_offset + k) * 4 + 0];
          break;
        case 'G':
        case 'g':
          score += pssm[(forward_offset + k) * 4 + 1];
          break;
        case 'C':
        case 'c':
          score += pssm[(forward_offset + k) * 4 + 2];
          break;
        case 'T':
        case 't':
          score += pssm[(forward_offset + k) * 4 + 3];
          break;
        }
      }
      score_matrix[(i * num_alignments) + j - forward_offset] = score;
    }
  }
}

static int matrix_converter(PyObject *object, void *address) {
  const int flags = PyBUF_C_CONTIGUOUS | PyBUF_FORMAT;
  char datatype;
  Py_buffer *view = address;

  if (object == NULL)
    goto exit;
  if (PyObject_GetBuffer(object, view, flags) == -1) {
    PyErr_SetString(PyExc_RuntimeError,
                    "position-weight matrix is not an array");
    return 0;
  }
  datatype = view->format[0];
  switch (datatype) {
  case '@':
  case '=':
  case '<':
  case '>':
  case '!':
    datatype = view->format[1];
    break;
  default:
    break;
  }
  return Py_CLEANUP_SUPPORTED;

exit:
  PyBuffer_Release(view);
  return 0;
}

static char calculate__doc__[] =
    "    calculate(sequence, recognizers, recognizer_lengths, connectors, "
    "recognizer_scores, connector_scores, connector_legnths)\n"
    "\n"
    "This function computes optimal placement for a \n"
    "transcription factor composed of PSSM recogniers\n"
    "and variable length connectors.\n";

static PyObject *py_calculate(PyObject *self, PyObject *args,
                              PyObject *keywords) {
  const char *seq;
  static char *kwlist[] = {
      "sequence",   "rec_matrices", "rec_lengths", "con_matrices",
      "rec_scores", "con_scores",   "con_lengths", "max_length", NULL};
  Py_ssize_t len_seq;
  Py_ssize_t num_rec;
  int max_length;
  PyObject *result = Py_None;
  Py_buffer rec_matrices;
  Py_buffer con_matrices;
  Py_buffer rec_lengths;
  Py_buffer rec_scores;
  Py_buffer con_scores;
  Py_buffer con_lengths;

  rec_matrices.obj = NULL;
  con_matrices.obj = NULL;
  rec_lengths.obj = NULL;
  rec_scores.obj = NULL;
  con_scores.obj = NULL;
  con_lengths.obj = NULL;
  if (!PyArg_ParseTupleAndKeywords(
          args, keywords, "y#O&O&O&O&O&O&i", kwlist, &seq, &len_seq,
          matrix_converter, &rec_matrices, matrix_converter, &rec_lengths,
          matrix_converter, &con_matrices, matrix_converter, &rec_scores,
          matrix_converter, &con_scores, matrix_converter, &con_lengths, &max_length))
    return NULL;

  // sequence:     DNA sequence used for placement
  // rec_matrices: one dimensional flattened representation of the
  //               scoring matrices for all recognizers
  // rec_lengths:  length of each recognizer (the number of columns)
  // con_matrices: one dimensional flattened representation of pre-computed
  //               scores for each connector for each gap length
  // rec_scores:   buffer used to store our calculated scores for recognizers
  // con_scores:   buffer used to score our calculated scores for connectors
  // con_lengths:  buffer used to store the length of each connector for our
  // placment
  num_rec = rec_lengths.shape[0];
  float *rec_matrices_ptr = rec_matrices.buf;
  float *con_matrices_ptr = con_matrices.buf;
  float *con_scores_ptr = con_scores.buf;
  float *rec_scores_ptr = rec_scores.buf;
  int *rec_lengths_ptr = rec_lengths.buf;
  int *con_lengths_ptr = con_lengths.buf;
  bool is_precomputed = true;
  // getting the number of alignments is needed for calculating the size
  // of the array we will use to store the scores for each recognizer alignment
  int forward_offset = get_forward_offset(0, rec_lengths_ptr, num_rec);
  int reverse_offset = get_reverse_offset(0, rec_lengths_ptr, num_rec);
  int num_alignments = len_seq - forward_offset - reverse_offset;
  float *score_matrix =
      PyMem_Calloc(num_alignments * num_rec, sizeof(*rec_matrices_ptr));
  fill_matrix(seq, len_seq, rec_matrices_ptr, rec_lengths_ptr, num_rec,
              score_matrix, num_alignments);

  if (con_matrices.shape[0] == (num_rec - 1) * 2)
    is_precomputed = false;
  // traceback function breaks when the number of recognizers is less than
  // two since it opperates on the assumption of having at least one connector
  if (num_rec == 1) {
    con_lengths_ptr[0] =
        max_index(score_matrix, len_seq - forward_offset - reverse_offset);
    rec_scores_ptr[0] = score_matrix[con_lengths_ptr[0]];
    con_scores_ptr[0] = 0.00;
  } else {
    fill_traceback_matrix(score_matrix, num_alignments, con_matrices_ptr, rec_lengths_ptr,
              num_rec, len_seq, con_scores_ptr, rec_scores_ptr,
              con_lengths_ptr, max_length, is_precomputed);
  }

  PyMem_Free(score_matrix);
  Py_INCREF(Py_None);
  result = Py_None;
  matrix_converter(NULL, &rec_matrices);
  matrix_converter(NULL, &rec_lengths);
  matrix_converter(NULL, &con_matrices);
  matrix_converter(NULL, &rec_scores);
  matrix_converter(NULL, &con_scores);
  matrix_converter(NULL, &con_lengths);
  return result;
}

static struct PyMethodDef methods[] = {
    {
        "calculate",
        (PyCFunction)py_calculate,
        METH_VARARGS | METH_KEYWORDS,
        PyDoc_STR(calculate__doc__),
    },
    {NULL, NULL, 0, NULL} // sentinel
};

static struct PyModuleDef moduledef = {
    PyModuleDef_HEAD_INIT,
    "_multiplacement",
    PyDoc_STR("Fast calculations involving multiple connected PSSMs"),
    -1,
    methods,
    NULL,
    NULL,
    NULL,
    NULL};

PyObject *PyInit__multiplacement(void) { return PyModule_Create(&moduledef); }