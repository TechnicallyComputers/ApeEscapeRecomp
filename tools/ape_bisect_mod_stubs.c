/* Weak stand-ins for mod APIs missing from older psxrecomp tips.
 * Strong definitions in runtime/src/main.cpp win when present; these only
 * satisfy the linker so Ape's plugin .c files can build against mid-rollback
 * history during memcard bisect. */
#include <stdint.h>

__attribute__((weak)) int psx_mod_set_frame_interpolation_blend(uint32_t blend_mode) {
    (void)blend_mode;
    return 0;
}

__attribute__((weak)) int psx_mod_set_frame_interpolation(uint32_t frames_per_second) {
    (void)frames_per_second;
    return 0;
}

__attribute__((weak)) int psx_mod_set_auto_skip_fmv(int enabled) {
    (void)enabled;
    return 0;
}

__attribute__((weak)) int psx_mod_set_fixed_display_aspect(uint32_t numerator,
                                                           uint32_t denominator) {
    (void)numerator;
    (void)denominator;
    return 0;
}

__attribute__((weak)) int psx_mod_set_adaptive_display_aspect(uint32_t max_numerator,
                                                              uint32_t max_denominator) {
    (void)max_numerator;
    (void)max_denominator;
    return 0;
}
