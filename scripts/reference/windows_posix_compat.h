/* Native Windows I/O compatibility for the unmodified Sail C runtime.
 * This affects the legacy text-image reader, not instruction semantics.
 * Force-include for C translation units only; never redefine std::getline.
 */
#ifndef RV23_SAIL_WINDOWS_POSIX_COMPAT_H
#define RV23_SAIL_WINDOWS_POSIX_COMPAT_H
#if defined(_WIN32) && !defined(__cplusplus)
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/types.h>

static inline ssize_t rv23_sail_getline(char **line, size_t *capacity, FILE *stream) {
    if (!line || !capacity || !stream) {
        errno = EINVAL;
        return -1;
    }
    if (!*line || *capacity < 2) {
        size_t initial = *capacity >= 128 ? *capacity : 128;
        char *replacement = (char *)realloc(*line, initial);
        if (!replacement) return -1;
        *line = replacement;
        *capacity = initial;
    }
    size_t length = 0;
    for (;;) {
        int value = fgetc(stream);
        if (value == EOF) break;
        if (length + 1 >= *capacity) {
            if (*capacity > SIZE_MAX / 2) {
                errno = ENOMEM;
                return -1;
            }
            size_t next = *capacity * 2;
            char *replacement = (char *)realloc(*line, next);
            if (!replacement) return -1;
            *line = replacement;
            *capacity = next;
        }
        (*line)[length++] = (char)value;
        if (value == '\n') break;
    }
    (*line)[length] = '\0';
    return length ? (ssize_t)length : -1;
}
#define getline rv23_sail_getline
#endif
#endif
