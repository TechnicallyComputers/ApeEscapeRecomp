#include "mod_plugins.h"

/*
 * Keep Ape Escape's guest cadence completely stock. These callbacks only
 * select how frequently PSXrecomp's OpenGL presentation thread blends between
 * the two most recent completed game frames.
 */
static void ape_frame_rate_60_activate(void) {
    (void)psx_mod_set_frame_interpolation(60u);
}

static void ape_frame_rate_120_activate(void) {
    (void)psx_mod_set_frame_interpolation(120u);
}

static void ape_frame_rate_144_activate(void) {
    (void)psx_mod_set_frame_interpolation(144u);
}

static void ape_frame_rate_165_activate(void) {
    (void)psx_mod_set_frame_interpolation(165u);
}

static void ape_frame_rate_uncapped_activate(void) {
    (void)psx_mod_set_frame_interpolation(0u);
}

PSX_MOD_CONSTRUCTOR(ape_register_frame_rate_plugins) {
    (void)psx_mod_register_activation_plugin(
        "ape.framerate.60", ape_frame_rate_60_activate);
    (void)psx_mod_register_activation_plugin(
        "ape.framerate.120", ape_frame_rate_120_activate);
    (void)psx_mod_register_activation_plugin(
        "ape.framerate.144", ape_frame_rate_144_activate);
    (void)psx_mod_register_activation_plugin(
        "ape.framerate.165", ape_frame_rate_165_activate);
    (void)psx_mod_register_activation_plugin(
        "ape.framerate.uncapped", ape_frame_rate_uncapped_activate);
}
