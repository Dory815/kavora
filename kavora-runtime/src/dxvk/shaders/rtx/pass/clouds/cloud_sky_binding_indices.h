/* SPDX-License-Identifier: MIT */
#pragma once

#include "rtx/pass/common_binding_indices.h"

#define CLOUD_SKY_BINDING_OUTPUT 42
#define CLOUD_SKY_BINDING_DISTANCE_MOMENT_OUTPUT 43

#if CLOUD_SKY_BINDING_OUTPUT <= COMMON_MAX_BINDING
#error "Cloud sky bindings overlap common bindings."
#endif
