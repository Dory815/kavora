# SPDX-FileCopyrightText: Copyright (c) 2026 GBwater
# SPDX-License-Identifier: MIT
"""Export the production Java/GLSL sky as input to render_cloud_preview.py.

Requires NumPy, the Python vulkan package, glslangValidator, a JDK supporting
Math.clamp, and a Vulkan ICD. No Minecraft window or replacement sky formula
is used: Java supplies the optical constants and altitude-dependent direct
light; the unmodified GLSL body executes all four production compute passes.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path
import subprocess
import tempfile

import numpy as np
import vulkan as vk


ROOT = Path(__file__).resolve().parents[4]


class SkyDevice:
    def __init__(self):
        self.instance = vk.vkCreateInstance(vk.VkInstanceCreateInfo(
            pApplicationInfo=vk.VkApplicationInfo(apiVersion=vk.VK_MAKE_VERSION(1, 1, 0))), None)
        self.physical = vk.vkEnumeratePhysicalDevices(self.instance)[0]
        families = vk.vkGetPhysicalDeviceQueueFamilyProperties(self.physical)
        self.family = next(i for i, f in enumerate(families) if f.queueFlags & vk.VK_QUEUE_COMPUTE_BIT)
        self.device = vk.vkCreateDevice(self.physical, vk.VkDeviceCreateInfo(
            queueCreateInfoCount=1, pQueueCreateInfos=[vk.VkDeviceQueueCreateInfo(
                queueFamilyIndex=self.family, queueCount=1, pQueuePriorities=[1.0])]), None)
        self.queue = vk.vkGetDeviceQueue(self.device, self.family, 0)
        self.memory = vk.vkGetPhysicalDeviceMemoryProperties(self.physical)
        self.buffers = []
        self.images = []
        self.pool = vk.vkCreateCommandPool(self.device, vk.VkCommandPoolCreateInfo(
            queueFamilyIndex=self.family), None)
        self.command = vk.vkAllocateCommandBuffers(self.device, vk.VkCommandBufferAllocateInfo(
            commandPool=self.pool, level=vk.VK_COMMAND_BUFFER_LEVEL_PRIMARY, commandBufferCount=1))[0]

    def allocate(self, requirements, flags):
        index = next(i for i in range(self.memory.memoryTypeCount)
                     if requirements.memoryTypeBits & (1 << i)
                     and self.memory.memoryTypes[i].propertyFlags & flags == flags)
        return vk.vkAllocateMemory(self.device, vk.VkMemoryAllocateInfo(
            allocationSize=requirements.size, memoryTypeIndex=index), None)

    def buffer(self, size, usage, data=None):
        buffer = vk.vkCreateBuffer(self.device, vk.VkBufferCreateInfo(size=size, usage=usage,
                                   sharingMode=vk.VK_SHARING_MODE_EXCLUSIVE), None)
        memory = self.allocate(vk.vkGetBufferMemoryRequirements(self.device, buffer),
                              vk.VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | vk.VK_MEMORY_PROPERTY_HOST_COHERENT_BIT)
        vk.vkBindBufferMemory(self.device, buffer, memory, 0)
        if data is not None:
            mapped = vk.vkMapMemory(self.device, memory, 0, size, 0)
            mapped[:] = data
            vk.vkUnmapMemory(self.device, memory)
        self.buffers.append((buffer, memory))
        return buffer, memory

    def image(self, width, height, format, dtype):
        image = vk.vkCreateImage(self.device, vk.VkImageCreateInfo(
            imageType=vk.VK_IMAGE_TYPE_2D, format=format, extent=vk.VkExtent3D(width, height, 1),
            mipLevels=1, arrayLayers=1, samples=vk.VK_SAMPLE_COUNT_1_BIT, tiling=vk.VK_IMAGE_TILING_OPTIMAL,
            usage=vk.VK_IMAGE_USAGE_STORAGE_BIT | vk.VK_IMAGE_USAGE_SAMPLED_BIT | vk.VK_IMAGE_USAGE_TRANSFER_SRC_BIT,
            sharingMode=vk.VK_SHARING_MODE_EXCLUSIVE, initialLayout=vk.VK_IMAGE_LAYOUT_UNDEFINED), None)
        memory = self.allocate(vk.vkGetImageMemoryRequirements(self.device, image), 0)
        vk.vkBindImageMemory(self.device, image, memory, 0)
        span = vk.VkImageSubresourceRange(vk.VK_IMAGE_ASPECT_COLOR_BIT, 0, 1, 0, 1)
        view = vk.vkCreateImageView(self.device, vk.VkImageViewCreateInfo(image=image,
            viewType=vk.VK_IMAGE_VIEW_TYPE_2D, format=format, subresourceRange=span), None)
        result = dict(image=image, memory=memory, view=view, span=span,
                      width=width, height=height, dtype=np.dtype(dtype))
        self.images.append(result)
        return result

    def render(self, spirv, parameters, width, height):
        lut = self.image(1024, 256, vk.VK_FORMAT_R32G32B32A32_SFLOAT, np.float32)
        scattering = self.image(64, 64, vk.VK_FORMAT_R32G32B32A32_SFLOAT, np.float32)
        sky = self.image(width, height + 1, vk.VK_FORMAT_R16G16B16A16_SFLOAT, np.float16)
        transmission = self.image(1, height, vk.VK_FORMAT_R16G16B16A16_SFLOAT, np.float16)
        uniform, _ = self.buffer(80, vk.VK_BUFFER_USAGE_UNIFORM_BUFFER_BIT, parameters.tobytes())
        sampler = vk.vkCreateSampler(self.device, vk.VkSamplerCreateInfo(
            magFilter=vk.VK_FILTER_LINEAR, minFilter=vk.VK_FILTER_LINEAR,
            mipmapMode=vk.VK_SAMPLER_MIPMAP_MODE_NEAREST,
            addressModeU=vk.VK_SAMPLER_ADDRESS_MODE_CLAMP_TO_EDGE,
            addressModeV=vk.VK_SAMPLER_ADDRESS_MODE_CLAMP_TO_EDGE,
            addressModeW=vk.VK_SAMPLER_ADDRESS_MODE_CLAMP_TO_EDGE, maxLod=0), None)
        types = [vk.VK_DESCRIPTOR_TYPE_STORAGE_IMAGE] * 3 + [vk.VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER] * 2
        types += [vk.VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER, vk.VK_DESCRIPTOR_TYPE_STORAGE_IMAGE]
        layout = vk.vkCreateDescriptorSetLayout(self.device, vk.VkDescriptorSetLayoutCreateInfo(
            bindingCount=7, pBindings=[vk.VkDescriptorSetLayoutBinding(
                binding=i, descriptorType=t, descriptorCount=1, stageFlags=vk.VK_SHADER_STAGE_COMPUTE_BIT)
                for i, t in enumerate(types)]), None)
        descriptors = vk.vkCreateDescriptorPool(self.device, vk.VkDescriptorPoolCreateInfo(
            maxSets=1, poolSizeCount=3, pPoolSizes=[vk.VkDescriptorPoolSize(t, n) for t, n in
                [(vk.VK_DESCRIPTOR_TYPE_STORAGE_IMAGE, 4),
                 (vk.VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER, 2), (vk.VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER, 1)]]), None)
        descriptor = vk.vkAllocateDescriptorSets(self.device, vk.VkDescriptorSetAllocateInfo(
            descriptorPool=descriptors, descriptorSetCount=1, pSetLayouts=[layout]))[0]
        writes = []
        for binding, image in ((0, lut), (1, scattering), (2, sky), (3, lut), (4, scattering), (6, transmission)):
            info = vk.VkDescriptorImageInfo(sampler=sampler if binding in (3, 4) else vk.VK_NULL_HANDLE,
                imageView=image['view'], imageLayout=vk.VK_IMAGE_LAYOUT_GENERAL)
            writes.append(vk.VkWriteDescriptorSet(dstSet=descriptor, dstBinding=binding,
                descriptorCount=1, descriptorType=types[binding], pImageInfo=[info]))
        writes.append(vk.VkWriteDescriptorSet(dstSet=descriptor, dstBinding=5, descriptorCount=1,
            descriptorType=types[5], pBufferInfo=[vk.VkDescriptorBufferInfo(uniform, 0, 80)]))
        vk.vkUpdateDescriptorSets(self.device, len(writes), writes, 0, None)
        pipeline_layout = vk.vkCreatePipelineLayout(self.device, vk.VkPipelineLayoutCreateInfo(
            setLayoutCount=1, pSetLayouts=[layout], pushConstantRangeCount=1,
            pPushConstantRanges=[vk.VkPushConstantRange(vk.VK_SHADER_STAGE_COMPUTE_BIT, 0, 4)]), None)
        shader = vk.vkCreateShaderModule(self.device, vk.VkShaderModuleCreateInfo(
            codeSize=len(spirv), pCode=spirv), None)
        # Keep the entry-point string alive through the binding's by-value stage copy.
        stage = vk.VkPipelineShaderStageCreateInfo(stage=vk.VK_SHADER_STAGE_COMPUTE_BIT,
                                                   module=shader, pName='main')
        pipeline = vk.vkCreateComputePipelines(self.device, vk.VK_NULL_HANDLE, 1,
            [vk.VkComputePipelineCreateInfo(layout=pipeline_layout, stage=stage)], None)[0]
        command = self.command
        vk.vkBeginCommandBuffer(command, vk.VkCommandBufferBeginInfo())
        barriers = [vk.VkImageMemoryBarrier(srcAccessMask=0,
            dstAccessMask=vk.VK_ACCESS_SHADER_READ_BIT | vk.VK_ACCESS_SHADER_WRITE_BIT,
            oldLayout=vk.VK_IMAGE_LAYOUT_UNDEFINED, newLayout=vk.VK_IMAGE_LAYOUT_GENERAL,
            srcQueueFamilyIndex=vk.VK_QUEUE_FAMILY_IGNORED, dstQueueFamilyIndex=vk.VK_QUEUE_FAMILY_IGNORED,
            image=image['image'], subresourceRange=image['span']) for image in self.images]
        vk.vkCmdPipelineBarrier(command, vk.VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT,
            vk.VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT, 0, 0, None, 0, None, len(barriers), barriers)
        vk.vkCmdBindPipeline(command, vk.VK_PIPELINE_BIND_POINT_COMPUTE, pipeline)
        vk.vkCmdBindDescriptorSets(command, vk.VK_PIPELINE_BIND_POINT_COMPUTE,
                                  pipeline_layout, 0, 1, [descriptor], 0, None)
        for pass_index, groups in enumerate(((128, 32), (8, 8), ((width + 7) // 8, (height + 7) // 8), (1, 1))):
            value = vk.ffi.new('int32_t *', pass_index)
            vk.vkCmdPushConstants(command, pipeline_layout, vk.VK_SHADER_STAGE_COMPUTE_BIT, 0, 4, value)
            vk.vkCmdDispatch(command, groups[0], groups[1], 1)
            barrier = vk.VkMemoryBarrier(srcAccessMask=vk.VK_ACCESS_SHADER_WRITE_BIT,
                                         dstAccessMask=vk.VK_ACCESS_SHADER_READ_BIT | vk.VK_ACCESS_SHADER_WRITE_BIT)
            vk.vkCmdPipelineBarrier(command, vk.VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT,
                vk.VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT, 0, 1, [barrier], 0, None, 0, None)
        copies = []
        for name, image in (('sky', sky), ('transmittance', transmission), ('lut', lut), ('scattering', scattering)):
            size = image['width'] * image['height'] * 4 * image['dtype'].itemsize
            buffer, memory = self.buffer(size, vk.VK_BUFFER_USAGE_TRANSFER_DST_BIT)
            barrier = vk.VkImageMemoryBarrier(srcAccessMask=vk.VK_ACCESS_SHADER_WRITE_BIT,
                dstAccessMask=vk.VK_ACCESS_TRANSFER_READ_BIT, oldLayout=vk.VK_IMAGE_LAYOUT_GENERAL,
                newLayout=vk.VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL,
                srcQueueFamilyIndex=vk.VK_QUEUE_FAMILY_IGNORED, dstQueueFamilyIndex=vk.VK_QUEUE_FAMILY_IGNORED,
                image=image['image'], subresourceRange=image['span'])
            vk.vkCmdPipelineBarrier(command, vk.VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT,
                vk.VK_PIPELINE_STAGE_TRANSFER_BIT, 0, 0, None, 0, None, 1, [barrier])
            region = vk.VkBufferImageCopy(imageSubresource=vk.VkImageSubresourceLayers(
                vk.VK_IMAGE_ASPECT_COLOR_BIT, 0, 0, 1), imageOffset=vk.VkOffset3D(0, 0, 0),
                imageExtent=vk.VkExtent3D(image['width'], image['height'], 1))
            vk.vkCmdCopyImageToBuffer(command, image['image'], vk.VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL,
                                     buffer, 1, [region])
            copies.append((name, memory, size, image))
        readback = vk.VkMemoryBarrier(srcAccessMask=vk.VK_ACCESS_TRANSFER_WRITE_BIT,
                                       dstAccessMask=vk.VK_ACCESS_HOST_READ_BIT)
        vk.vkCmdPipelineBarrier(command, vk.VK_PIPELINE_STAGE_TRANSFER_BIT,
            vk.VK_PIPELINE_STAGE_HOST_BIT, 0, 1, [readback], 0, None, 0, None)
        vk.vkEndCommandBuffer(command)
        vk.vkQueueSubmit(self.queue, 1, [vk.VkSubmitInfo(commandBufferCount=1, pCommandBuffers=[command])], vk.VK_NULL_HANDLE)
        vk.vkQueueWaitIdle(self.queue)
        result = {}
        for name, memory, size, image in copies:
            data = vk.vkMapMemory(self.device, memory, 0, size, 0)
            result[name] = np.frombuffer(data, dtype=image['dtype']).copy().reshape(image['height'], image['width'], 4)
            vk.vkUnmapMemory(self.device, memory)
        vk.vkDestroyPipeline(self.device, pipeline, None)
        vk.vkDestroyShaderModule(self.device, shader, None)
        vk.vkDestroyPipelineLayout(self.device, pipeline_layout, None)
        vk.vkDestroyDescriptorPool(self.device, descriptors, None)
        vk.vkDestroyDescriptorSetLayout(self.device, layout, None)
        vk.vkDestroySampler(self.device, sampler, None)
        for image in self.images:
            vk.vkDestroyImageView(self.device, image['view'], None)
            vk.vkDestroyImage(self.device, image['image'], None)
            vk.vkFreeMemory(self.device, image['memory'], None)
        for buffer, memory in self.buffers:
            vk.vkDestroyBuffer(self.device, buffer, None)
            vk.vkFreeMemory(self.device, memory, None)
        vk.vkDestroyCommandPool(self.device, self.pool, None)
        vk.vkDestroyDevice(self.device, None)
        vk.vkDestroyInstance(self.instance, None)
        return result


def java_inputs(args, directory):
    source = args.repo / 'kavora/src/main/java/org/edtp/kavora/sky/SkyAtmosphere.java'
    helper = directory / 'SkyFixture.java'
    helper.write_text('''package org.edtp.kavora.sky;
import java.nio.file.*;
import java.util.Arrays;
public final class SkyFixture {
  public static void main(String[] args) throws Exception {
    Files.writeString(Path.of(args[0]), SkyAtmosphere.shaderDefinitions());
    float elevation = Float.parseFloat(args[1]);
    float source = Float.parseFloat(args[2]) * (float)Math.PI;
    float sea = Float.parseFloat(args[3]);
    float[] heights = new float[4];
    for (int i=0;i<4;i++) heights[i] = Float.parseFloat(args[4+i]);
    float[] profile = new float[16];
    SkyAtmosphere.radianceProfile(profile, heights, sea, new float[]{source,source,source},
      (float)Math.sin(Math.toRadians(elevation)), 0.004625123f);
    float observer = SkyAtmosphere.observerHeight(Float.parseFloat(args[8]) - sea);
    float[] surface = SkyAtmosphere.transmittanceToLight(observer,
      (float)Math.sin(Math.toRadians(elevation)), 0.004625123f);
    for (int i=0;i<3;i++) surface[i] *= source;
    System.out.println(Arrays.toString(profile));
    System.out.println(Arrays.toString(surface));
    System.out.println(observer);
  }
}
''')
    compiler = [args.javac] if args.javac else [args.java, 'com.sun.tools.javac.Main']
    subprocess.run([*compiler, '-d', str(directory), str(source), str(helper)], check=True)
    definitions = directory / 'definitions.glsl'
    lighting = subprocess.check_output([args.java, '-cp', str(directory), 'org.edtp.kavora.sky.SkyFixture',
        str(definitions), str(args.sun_elevation), str(args.sun_radiance), str(args.sea_level),
        *map(str, args.profile_heights), str(args.world_height)], text=True).splitlines()
    return definitions.read_text(), dict(cloudIrradianceProfile=json.loads(lighting[0]),
                                        surfaceIrradiance=json.loads(lighting[1]),
                                        observerHeight=float(lighting[2]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=ROOT)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--sun-elevation', type=float, default=40)
    parser.add_argument('--sun-azimuth', type=float, default=135)
    parser.add_argument('--sun-radiance', type=float, default=30)
    parser.add_argument('--world-height', type=float, default=139)
    parser.add_argument('--sea-level', type=float, default=63)
    parser.add_argument('--profile-heights', type=float, nargs=4, default=[800, 2300, 6300, 6500])
    parser.add_argument('--width', type=int, default=512)
    parser.add_argument('--height', type=int, default=512)
    parser.add_argument('--mie-anisotropy', type=float, default=0.9)
    parser.add_argument('--glslang', default='glslangValidator')
    parser.add_argument('--javac', help='Compiler executable; defaults to the selected Java compiler module')
    parser.add_argument('--java', default='java')
    args = parser.parse_args()
    if args.width < 8 or args.height < 4 or args.height % 2:
        parser.error('width must be >= 8 and height must be even and >= 4')
    if not np.isfinite([args.sun_elevation, args.sun_azimuth, args.sun_radiance,
                       args.world_height, args.sea_level, args.mie_anisotropy,
                       *args.profile_heights]).all():
        parser.error('sky parameters must be finite')
    if not -90 <= args.sun_elevation <= 90 or args.sun_radiance < 0:
        parser.error('sun elevation must be in [-90,90] and radiance nonnegative')
    if not 0 <= args.mie_anisotropy < 1:
        parser.error('Mie anisotropy must be in [0,1)')
    if np.any(np.diff(args.profile_heights) <= 0):
        parser.error('profile heights must be strictly increasing')
    args.output.mkdir(parents=True, exist_ok=True)
    sky_path = args.repo / 'kavora/src/main/resources/assets/kavora/shaders/sky_atmosphere.comp'
    with tempfile.TemporaryDirectory(prefix='cloud-atmosphere-') as temporary:
        temporary = Path(temporary)
        definitions, lighting = java_inputs(args, temporary)
        source = sky_path.read_text()
        end = source.index('\n', source.index('#version')) + 1
        source = source[:end] + definitions + f'\n#define SKY_WIDTH {args.width}\n#define SKY_HEIGHT {args.height}\n#define SKY_VERTICAL_SCALE 4.0\n' + source[end:]
        generated = temporary / 'sky.comp'
        generated.write_text(source)
        binary = temporary / 'sky.spv'
        subprocess.run([args.glslang, '-V', '--target-env', 'vulkan1.1', str(generated), '-o', str(binary)], check=True)
        (args.output / 'sky.spv').write_bytes(binary.read_bytes())
        elevation, azimuth = np.radians([args.sun_elevation, args.sun_azimuth])
        sun = [np.sin(azimuth) * np.cos(elevation), np.sin(elevation), np.cos(azimuth) * np.cos(elevation)]
        # AtmosphericSkyGenerator.setSkyTextureDirection mirrors X before
        # dispatch. The dome's longitude convention mirrors it back at sampling.
        # Keep the cloud light and manifest in world space.
        texture_sun = [-sun[0], sun[1], sun[2]]
        parameters = np.array([*texture_sun, 0.004625123, *(-np.array(texture_sun)), 0.004625123,
                               *([args.sun_radiance * np.pi] * 3), 0, 0, 0, 0, 0,
                               args.mie_anisotropy, lighting['observerHeight'], 0, 0], np.float32)
        data = SkyDevice().render(binary.read_bytes(), parameters, args.width, args.height)
    valid = {k:v for k,v in data.items() if k != 'sky'}
    valid.update(sky=data['sky'][:args.height], irradiance=data['sky'][args.height, 0])
    if not all(np.isfinite(value).all() for value in valid.values()):
        raise RuntimeError('Nonfinite atmosphere output')
    np.savez_compressed(args.output / 'atmosphere.npz', **valid)
    constants = dict(re.findall(r'^#define (\w+) (.+)$', definitions, re.MULTILINE))
    optical_model = {field: float(constants[name]) for field, name in (
        ('innerRadius', 'INNER_RADIUS'), ('lowerDepth', 'LOWER_DEPTH'),
        ('atmosphereHeight', 'ATMOSPHERE_HEIGHT'), ('rayleighHeight', 'RAYLEIGH_HEIGHT'),
        ('mieHeight', 'MIE_HEIGHT'), ('mieExtinction', 'BETA_M'), ('mieAlbedo', 'MIE_ALBEDO'))}
    optical_model['rayleighExtinction'] = [float(value) for value in
        constants['BETA_R'].removeprefix('vec3(').removesuffix(')').split(',')]
    manifest = dict(worldHeight=args.world_height, seaLevel=args.sea_level, sunDirection=sun,
        exporterHash=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        sunElevationDegrees=args.sun_elevation, sunAzimuthDegrees=args.sun_azimuth, verticalScale=4.0,
        skyExtent=[args.width, args.height], sunSourceRadiance=args.sun_radiance,
        javaLighting=lighting, mieAnisotropy=args.mie_anisotropy, opticalModel=optical_model,
        textureSunDirection=texture_sun,
        sources={str(p.relative_to(args.repo)):hashlib.sha256(p.read_bytes()).hexdigest() for p in
          [sky_path, args.repo / 'kavora/src/main/java/org/edtp/kavora/sky/SkyAtmosphere.java',
           args.repo / 'kavora/src/main/java/org/edtp/kavora/sky/AtmosphericSkyGenerator.java',
           args.repo / 'kavora-sdk/src/org/edtp/kavora/sdk/LightInfoDomeEXT.java']},
        scope='Actual production Java profile and four GLSL passes; no game window, terrain or sun disk')
    (args.output / 'manifest.json').write_text(json.dumps(manifest, indent=2))
    print('Saved production atmosphere', args.output, flush=True)


if __name__ == '__main__':
    main()
