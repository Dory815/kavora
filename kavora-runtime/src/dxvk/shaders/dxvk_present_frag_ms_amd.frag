#version 450

// NV-DXVK start: Share the display transfer functions.
#extension GL_GOOGLE_include_directive: require
// NV-DXVK end

#extension GL_AMD_shader_fragment_mask: enable

layout(constant_id = 1) const bool s_gamma_bound = true;
layout(constant_id = 1225) const uint c_samples = 0;

layout(binding = 0) uniform sampler2DMS s_image;
layout(binding = 1) uniform sampler1D s_gamma;

layout(location = 0) out vec4 o_color;

layout(push_constant)
uniform present_info_t {
  ivec2 src_offset;
  ivec2 dst_offset;
  // NV-DXVK start: Host framebuffer orientation.
  uint bottom_up;
  uint source_height;
  // NV-DXVK end
  // NV-DXVK start: The output encoding is fixed for this presentation.
  uint display_transfer;
  uint display_frame_index;
  float source_paper_white_nits;
  float source_peak_nits;
  float target_paper_white_nits;
  float target_peak_nits;
  // NV-DXVK end

};

// NV-DXVK start: The final pass owns display encoding.
#include "dxvk_present_color.glsl"
// NV-DXVK end

void main() {
  ivec2 coord = ivec2(gl_FragCoord.xy) + src_offset - dst_offset;
  // NV-DXVK start: Apply the same orientation to multisample sources.
  if (bottom_up != 0) {
    coord.y = src_offset.y + int(source_height) - 1 - (int(gl_FragCoord.y) - dst_offset.y);
  }
  // NV-DXVK end

  // check dxvk_resolve_frag_f_amd.frag for documentation
  uint fragMask = fragmentMaskFetchAMD(s_image, coord);
  uint fragCount = 0u;

  for (int i = 0; i < 4 * c_samples; i += 4) {
    uint fragIndex = bitfieldExtract(fragMask, i, 4);
    fragCount += 1u << (fragIndex << 2);
  }

  o_color = vec4(0.0f);
  
  while (fragCount != 0) {
    int fragIndex = findLSB(fragCount) >> 2;
    int fragShift = fragIndex << 2;

    o_color += fragmentFetchAMD(s_image, coord, fragIndex)
      * float(bitfieldExtract(fragCount, fragShift, 4));

    fragCount = bitfieldInsert(fragCount, 0, fragShift, 4);
  }

  o_color /= float(c_samples);

  // NV-DXVK start: Legacy gamma ramps do not apply to explicit display encoding.
  if ((display_transfer & 255u) != 0u) {
    o_color.rgb = presentDisplayColor(o_color.rgb, uvec2(gl_FragCoord.xy));
  } else if (s_gamma_bound) {
  // NV-DXVK end
    o_color = vec4(
      texture(s_gamma, o_color.r).r,
      texture(s_gamma, o_color.g).g,
      texture(s_gamma, o_color.b).b,
      o_color.a);
  }
}