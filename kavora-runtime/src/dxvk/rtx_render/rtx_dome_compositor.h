/* SPDX-License-Identifier: MIT */
#pragma once

#include <vector>

#include "rtx_lights.h"
#include "rtx_night_sky.h"

namespace dxvk {
  class RtxContext;

  class DomeCompositor {
  public:
    // Composes in submission order into a shared environment sampled by every sky ray path.
    const TextureRef& compose(const Rc<RtxContext>& ctx, const std::vector<const DomeLight*>& layers, bool finiteAir);
    const TextureRef& background() const { return m_background.view.ptr() ? m_background.texture : m_environment.texture; }
    const TextureRef& boundary() const { return m_boundary.texture; }
    const TextureRef& backgroundBoundary() const { return m_background.view.ptr() ? m_background.texture : m_boundary.texture; }
    const Matrix4& worldToOutput() const { return m_worldToOutput; }

  private:
    struct Output {
      Rc<DxvkImage> image;
      Rc<DxvkImageView> view;
      TextureRef texture;
    };
    Output m_environment;
    Output m_background;
    Output m_boundary;
    Matrix4 m_worldToOutput;
    NightSky m_nightSky;
  };
}
