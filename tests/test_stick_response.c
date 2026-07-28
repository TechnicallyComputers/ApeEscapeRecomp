#include "psx_stick.h"

#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

enum {
    APE_HOST_DEADZONE = 3277,
    APE_ANTI_DEADZONE = 5376
};

static int axis_from_byte(uint8_t value)
{
    return (int)value - 128;
}

static double vector_magnitude(uint8_t x, uint8_t y)
{
    const double sx = (double)axis_from_byte(x);
    const double sy = (double)axis_from_byte(y);
    return sqrt(sx * sx + sy * sy);
}

/* The response recovered from Ape Escape's own DualShock processing. */
static double ape_response(double input_magnitude)
{
    if (input_magnitude < 21.0)
        return 0.0;
    input_magnitude = (input_magnitude - 21.0) * 127.0 / 106.0;
    return input_magnitude > 127.0 ? 127.0 : input_magnitude;
}

static void fail(const char *message)
{
    fprintf(stderr, "FAIL: %s\n", message);
    exit(1);
}

static void expect_near(double actual, double expected, double tolerance,
                        const char *message)
{
    if (fabs(actual - expected) > tolerance) {
        fprintf(stderr, "FAIL: %s (actual %.3f, expected %.3f +/- %.3f)\n",
                message, actual, expected, tolerance);
        exit(1);
    }
}

int main(void)
{
    uint8_t x;
    uint8_t y;
    double cardinal;
    double diagonal;
    double expected_response;
    int raw_midpoint;
    int degrees;

    psx_stick_to_dualshock(0, 0, APE_HOST_DEADZONE, APE_ANTI_DEADZONE, &x, &y);
    if (x != 0x80 || y != 0x80)
        fail("centre must remain exactly neutral");

    psx_stick_to_dualshock(APE_HOST_DEADZONE, 0,
                           APE_HOST_DEADZONE, APE_ANTI_DEADZONE, &x, &y);
    if (x != 0x80 || y != 0x80)
        fail("the host deadzone boundary must remain neutral");

    psx_stick_to_dualshock(32767, 32767, 32767, 0, &x, &y);
    if (x != 0x80 || y != 0x80)
        fail("a 100% deadzone must suppress square host diagonals");

    psx_stick_to_dualshock(APE_HOST_DEADZONE + 1, 0,
                           APE_HOST_DEADZONE, APE_ANTI_DEADZONE, &x, &y);
    expect_near(ape_response(vector_magnitude(x, y)), 0.0, 1.25,
                "anti-deadzone onset must be continuous through Ape's threshold");

    psx_stick_to_dualshock(-(APE_HOST_DEADZONE + 1), 0,
                           APE_HOST_DEADZONE, APE_ANTI_DEADZONE, &x, &y);
    expect_near(ape_response(vector_magnitude(x, y)), 0.0, 1.25,
                "negative anti-deadzone onset must also be continuous");

    psx_stick_to_dualshock(32767, 0,
                           APE_HOST_DEADZONE, APE_ANTI_DEADZONE, &x, &y);
    cardinal = ape_response(vector_magnitude(x, y));
    expect_near(cardinal, 127.0, 0.01, "full cardinal travel");

    psx_stick_to_dualshock(-32768, 0,
                           APE_HOST_DEADZONE, APE_ANTI_DEADZONE, &x, &y);
    expect_near(ape_response(vector_magnitude(x, y)), cardinal, 0.01,
                "positive and negative full travel must have equal speed");

    psx_stick_to_dualshock(23170, 23170,
                           APE_HOST_DEADZONE, APE_ANTI_DEADZONE, &x, &y);
    diagonal = ape_response(vector_magnitude(x, y));
    expect_near(diagonal, cardinal, 0.01,
                "full diagonal and cardinal travel must have equal speed");
    expect_near((double)axis_from_byte(x), (double)axis_from_byte(y), 0.01,
                "45-degree input must remain 45 degrees");

    psx_stick_to_dualshock(32767, 32767,
                           APE_HOST_DEADZONE, APE_ANTI_DEADZONE, &x, &y);
    expect_near(ape_response(vector_magnitude(x, y)), cardinal, 0.01,
                "square host diagonals must clamp to the same radial speed");

    raw_midpoint = APE_HOST_DEADZONE + (32767 - APE_HOST_DEADZONE) / 2;
    psx_stick_to_dualshock((int16_t)raw_midpoint, 0,
                           APE_HOST_DEADZONE, APE_ANTI_DEADZONE, &x, &y);
    expect_near(ape_response(vector_magnitude(x, y)), 63.5, 1.5,
                "half physical travel must produce half in-game speed");

    psx_stick_to_dualshock(10813, 14417,
                           APE_HOST_DEADZONE, APE_ANTI_DEADZONE, &x, &y);
    expect_near((double)axis_from_byte(x) / (double)axis_from_byte(y),
                0.75, 0.03, "off-axis direction must be preserved");

    expected_response = (20000.0 - APE_HOST_DEADZONE) * 127.0 /
                        (32767.0 - APE_HOST_DEADZONE);
    for (degrees = 0; degrees <= 90; degrees += 5) {
        const double radians = (double)degrees * acos(-1.0) / 180.0;
        const int16_t raw_x = (int16_t)lround(cos(radians) * 20000.0);
        const int16_t raw_y = (int16_t)lround(sin(radians) * 20000.0);
        double actual_degrees;

        psx_stick_to_dualshock(raw_x, raw_y,
                               APE_HOST_DEADZONE, APE_ANTI_DEADZONE, &x, &y);
        expect_near(ape_response(vector_magnitude(x, y)),
                    expected_response, 1.5,
                    "speed must remain constant through a 90-degree sweep");

        actual_degrees = atan2((double)axis_from_byte(y),
                               (double)axis_from_byte(x)) * 180.0 / acos(-1.0);
        expect_near(actual_degrees, (double)degrees, 1.0,
                    "direction must remain accurate through a 90-degree sweep");
    }

    psx_stick_to_dualshock(16384, 0, 0, 0, &x, &y);
    if (x != 192 || y != 128)
        fail("anti_deadzone=0 must preserve the ordinary radial mapping");

    puts("Ape Escape stick response tests passed");
    return 0;
}
