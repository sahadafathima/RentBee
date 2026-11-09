import { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import {
  ZoomIn,
  ZoomOut,
  RotateCw,
  RefreshCw,
  Check,
  X,
  Crop,
  ArrowRight,
  Eye,
} from 'lucide-react'

// Standard aspect ratio presets
const ASPECT_RATIOS = [
  { label: '4:3 (Catalog)', value: 4 / 3 },
  { label: '1:1 (Square)', value: 1 / 1 },
  { label: '16:9 (Wide)', value: 16 / 9 },
  { label: 'Free', value: null },
]

export default function ImageCropModal({
  files = [],
  initialIndex = 0,
  onComplete,
  onClose,
}) {
  const [currentIndex, setCurrentIndex] = useState(initialIndex)
  const [processedFiles, setProcessedFiles] = useState([])

  const currentFile = files[currentIndex]
  const isLast = currentIndex === files.length - 1

  const handleApplySingle = (croppedFile) => {
    const nextList = [...processedFiles, croppedFile]
    setProcessedFiles(nextList)

    if (isLast) {
      onComplete(nextList)
    } else {
      setCurrentIndex((i) => i + 1)
    }
  }

  const handleSkipSingle = () => {
    const nextList = [...processedFiles, currentFile]
    setProcessedFiles(nextList)

    if (isLast) {
      onComplete(nextList)
    } else {
      setCurrentIndex((i) => i + 1)
    }
  }

  if (!currentFile) return null

  return (
    <SingleImageCropper
      key={`${currentIndex}-${currentFile.name}-${currentFile.size}`}
      file={currentFile}
      index={currentIndex}
      total={files.length}
      isLast={isLast}
      onApply={handleApplySingle}
      onSkip={handleSkipSingle}
      onClose={onClose}
    />
  )
}

function SingleImageCropper({
  file,
  index,
  total,
  isLast,
  onApply,
  onSkip,
  onClose,
}) {
  const imageSrc = useMemo(() => URL.createObjectURL(file), [file])
  const [naturalDimensions, setNaturalDimensions] = useState({ width: 0, height: 0 })
  const [aspectRatio, setAspectRatio] = useState(4 / 3)
  const [zoom, setZoom] = useState(1)
  const [rotation, setRotation] = useState(0)
  const [pan, setPan] = useState({ x: 0, y: 0 })
  const [isDragging, setIsDragging] = useState(false)
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 })
  const [livePreviewUrl, setLivePreviewUrl] = useState('')
  const [showLivePreview, setShowLivePreview] = useState(false)
  const [isProcessing, setIsProcessing] = useState(false)

  const imageRef = useRef(null)
  const viewportRef = useRef(null)

  useEffect(() => {
    return () => {
      URL.revokeObjectURL(imageSrc)
    }
  }, [imageSrc])

  const handleImageLoad = (e) => {
    const { naturalWidth, naturalHeight } = e.target
    setNaturalDimensions({ width: naturalWidth, height: naturalHeight })
  }

  // Calculate visual crop box size inside viewport
  const getCropBoxDimensions = useCallback(() => {
    const maxW = 460
    const maxH = 345

    if (!aspectRatio) {
      if (!naturalDimensions.width || !naturalDimensions.height) {
        return { width: maxW, height: maxH }
      }
      const natR = naturalDimensions.width / naturalDimensions.height
      if (natR >= 1) {
        const w = maxW
        const h = Math.min(maxH, Math.round(maxW / natR))
        return { width: w, height: h }
      } else {
        const h = maxH
        const w = Math.min(maxW, Math.round(maxH * natR))
        return { width: w, height: h }
      }
    }

    if (aspectRatio >= 1) {
      const w = maxW
      const h = Math.round(maxW / aspectRatio)
      if (h > maxH) {
        return { width: Math.round(maxH * aspectRatio), height: maxH }
      }
      return { width: w, height: h }
    } else {
      const h = maxH
      const w = Math.round(maxH * aspectRatio)
      return { width: w, height: h }
    }
  }, [aspectRatio, naturalDimensions])

  const cropBox = getCropBoxDimensions()

  // Calculate image fit scale inside the crop box
  const getFitScale = useCallback(() => {
    if (!naturalDimensions.width || !naturalDimensions.height) return 1
    const isSideways = rotation % 180 !== 0
    const effectiveW = isSideways ? naturalDimensions.height : naturalDimensions.width
    const effectiveH = isSideways ? naturalDimensions.width : naturalDimensions.height

    return Math.max(cropBox.width / effectiveW, cropBox.height / effectiveH)
  }, [naturalDimensions, rotation, cropBox.width, cropBox.height])

  // Clamp pan so image covers the crop box
  const clampPan = useCallback(
    (newPan, currentZoom = zoom) => {
      if (!naturalDimensions.width || !naturalDimensions.height) return newPan
      const isSideways = rotation % 180 !== 0
      const effectiveW = isSideways ? naturalDimensions.height : naturalDimensions.width
      const effectiveH = isSideways ? naturalDimensions.width : naturalDimensions.height

      const fitScale = Math.max(cropBox.width / effectiveW, cropBox.height / effectiveH)
      const displayedW = effectiveW * fitScale * currentZoom
      const displayedH = effectiveH * fitScale * currentZoom

      const maxPanX = Math.max(0, (displayedW - cropBox.width) / 2)
      const maxPanY = Math.max(0, (displayedH - cropBox.height) / 2)

      return {
        x: Math.max(-maxPanX, Math.min(maxPanX, newPan.x)),
        y: Math.max(-maxPanY, Math.min(maxPanY, newPan.y)),
      }
    },
    [naturalDimensions, rotation, cropBox.width, cropBox.height, zoom]
  )

  // Zoom handlers
  const handleZoomChange = (newZoom) => {
    const clamped = Math.max(1, Math.min(3, newZoom))
    setZoom(clamped)
    setPan((prev) => clampPan(prev, clamped))
  }

  // Pointer drag to pan
  const handlePointerDown = (e) => {
    setIsDragging(true)
    setDragStart({ x: e.clientX - pan.x, y: e.clientY - pan.y })
  }

  const handlePointerMove = (e) => {
    if (!isDragging) return
    const rawPan = {
      x: e.clientX - dragStart.x,
      y: e.clientY - dragStart.y,
    }
    setPan(clampPan(rawPan))
  }

  const handlePointerUp = () => {
    setIsDragging(false)
  }

  // Mouse wheel zoom
  const handleWheel = (e) => {
    e.preventDefault()
    const delta = e.deltaY < 0 ? 0.1 : -0.1
    handleZoomChange(zoom + delta)
  }

  // Rotate handler
  const handleRotate = (deg = 90) => {
    setRotation((r) => (r + deg + 360) % 360)
    setPan({ x: 0, y: 0 })
  }

  // Reset handler
  const handleReset = () => {
    setZoom(1)
    setRotation(0)
    setPan({ x: 0, y: 0 })
  }

  // Render cropped image to high-resolution Canvas and export File
  const generateCroppedFile = useCallback(async () => {
    if (!imageRef.current || !naturalDimensions.width) {
      return file
    }

    const fitScale = Math.max(cropBox.width / naturalDimensions.width, cropBox.height / naturalDimensions.height)

    // Standardize target export resolution (max 1200x900)
    const targetMax = 1200
    const cropR = cropBox.width / cropBox.height
    let targetW, targetH
    if (cropR >= 1) {
      targetW = targetMax
      targetH = Math.round(targetMax / cropR)
    } else {
      targetH = targetMax
      targetW = Math.round(targetMax * cropR)
    }

    const canvas = document.createElement('canvas')
    canvas.width = targetW
    canvas.height = targetH
    const ctx = canvas.getContext('2d')

    ctx.imageSmoothingEnabled = true
    ctx.imageSmoothingQuality = 'high'

    const scaleToCanvas = targetW / cropBox.width

    ctx.save()
    ctx.translate(targetW / 2 + pan.x * scaleToCanvas, targetH / 2 + pan.y * scaleToCanvas)
    ctx.rotate((rotation * Math.PI) / 180)

    const drawW = naturalDimensions.width * fitScale * zoom * scaleToCanvas
    const drawH = naturalDimensions.height * fitScale * zoom * scaleToCanvas

    ctx.drawImage(imageRef.current, -drawW / 2, -drawH / 2, drawW, drawH)
    ctx.restore()

    return new Promise((resolve) => {
      canvas.toBlob(
        (blob) => {
          if (!blob) {
            resolve(file)
            return
          }
          const originalName = file.name || 'image.jpg'
          const baseName = originalName.substring(0, originalName.lastIndexOf('.')) || originalName
          const newFileName = `${baseName}_cropped.jpg`
          const croppedFile = new File([blob], newFileName, {
            type: 'image/jpeg',
            lastModified: Date.now(),
          })
          resolve(croppedFile)
        },
        'image/jpeg',
        0.92
      )
    })
  }, [file, naturalDimensions, rotation, cropBox, zoom, pan])

  // Update live preview when controls change
  useEffect(() => {
    let active = true
    if (!showLivePreview || !naturalDimensions.width) return

    generateCroppedFile().then((cropped) => {
      if (!active || !cropped) return
      const url = URL.createObjectURL(cropped)
      setLivePreviewUrl((prev) => {
        if (prev) URL.revokeObjectURL(prev)
        return url
      })
    })

    return () => {
      active = false
    }
  }, [zoom, pan, rotation, aspectRatio, showLivePreview, generateCroppedFile, naturalDimensions.width])

  // Apply crop for current image
  const handleApply = async () => {
    setIsProcessing(true)
    try {
      const croppedFile = await generateCroppedFile()
      onApply(croppedFile)
    } catch (err) {
      console.error('Error generating cropped image:', err)
      onApply(file)
    } finally {
      setIsProcessing(false)
    }
  }

  const fitScale = getFitScale()
  const imgDisplayW = naturalDimensions.width * fitScale * zoom
  const imgDisplayH = naturalDimensions.height * fitScale * zoom

  return (
    <div
      className="fixed inset-0 z-60 flex items-center justify-center p-3 sm:p-5 bg-black/70 backdrop-blur-xs select-none"
      onPointerUp={handlePointerUp}
    >
      <div className="flex flex-col w-full max-w-2xl max-h-[96vh] rounded-2xl border border-orange-100 bg-[#FFFCF9] text-[#302820] shadow-2xl overflow-hidden">
        {/* Modal Header */}
        <div className="flex items-center justify-between border-b border-orange-100 px-5 py-3.5 bg-white">
          <div className="flex items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-[#FFF0E7] text-[#9D4C29]">
              <Crop size={18} />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-base font-bold text-[#302820]">Crop & Resize Image</h3>
                {total > 1 && (
                  <span className="rounded-full bg-orange-100 px-2 py-0.5 text-[11px] font-bold text-[#9D4C29]">
                    {index + 1} of {total}
                  </span>
                )}
              </div>
              <p className="text-xs text-gray-500 truncate max-w-xs sm:max-w-md">
                {file.name} ({(file.size / (1024 * 1024)).toFixed(2)} MB)
              </p>
            </div>
          </div>

          <button
            type="button"
            onClick={onClose}
            className="p-1.5 text-gray-400 hover:text-gray-600 rounded-lg hover:bg-gray-100 transition cursor-pointer"
            title="Cancel and close"
          >
            <X size={18} />
          </button>
        </div>

        {/* Modal Body */}
        <div className="flex flex-col flex-1 overflow-y-auto p-4 sm:p-5 gap-4">
          {/* Multi-step progress bar */}
          {total > 1 && (
            <div className="flex items-center gap-1.5">
              {Array.from({ length: total }).map((_, idx) => (
                <div
                  key={idx}
                  className={`h-1.5 flex-1 rounded-full transition-all ${
                    idx < index
                      ? 'bg-[#9D4C29]'
                      : idx === index
                      ? 'bg-[#D97745]'
                      : 'bg-orange-100'
                  }`}
                />
              ))}
            </div>
          )}

          {/* Crop Viewport Container */}
          <div
            ref={viewportRef}
            className="relative flex items-center justify-center w-full h-80 sm:h-96 rounded-xl bg-[#1f1915] overflow-hidden cursor-grab active:cursor-grabbing border border-orange-950/20"
            onPointerDown={handlePointerDown}
            onPointerMove={handlePointerMove}
            onWheel={handleWheel}
          >
            {/* Dark Mask & Crop Window */}
            <div
              style={{
                width: `${cropBox.width}px`,
                height: `${cropBox.height}px`,
              }}
              className="relative overflow-hidden rounded-lg shadow-[0_0_0_9999px_rgba(0,0,0,0.65)] border-2 border-white/90 transition-all pointer-events-none"
            >
              {/* Rule of Thirds Grid Overlay */}
              <div className="absolute inset-0 grid grid-cols-3 grid-rows-3 pointer-events-none opacity-40">
                <div className="border-r border-b border-white/60" />
                <div className="border-r border-b border-white/60" />
                <div className="border-b border-white/60" />
                <div className="border-r border-b border-white/60" />
                <div className="border-r border-b border-white/60" />
                <div className="border-b border-white/60" />
                <div className="border-r border-white/60" />
                <div className="border-r border-white/60" />
                <div />
              </div>

              {/* Centered Image with Transforms */}
              {imageSrc && (
                <img
                  ref={imageRef}
                  src={imageSrc}
                  alt="Crop Target"
                  onLoad={handleImageLoad}
                  draggable={false}
                  style={{
                    position: 'absolute',
                    left: '50%',
                    top: '50%',
                    width: `${imgDisplayW}px`,
                    height: `${imgDisplayH}px`,
                    transform: `translate(-50%, -50%) translate(${pan.x}px, ${pan.y}px) rotate(${rotation}deg)`,
                    transformOrigin: 'center center',
                    maxWidth: 'none',
                    maxHeight: 'none',
                  }}
                  className="pointer-events-none select-none transition-transform duration-75"
                />
              )}
            </div>

            {/* Helper Hint */}
            <div className="absolute bottom-2.5 left-3 text-[11px] font-medium text-white/70 bg-black/60 px-2.5 py-1 rounded-md backdrop-blur-xs pointer-events-none">
              Drag to reposition • Scroll or use slider to zoom
            </div>
          </div>

          {/* Aspect Ratio Presets */}
          <div className="flex flex-wrap items-center justify-between gap-2 pt-1">
            <span className="text-xs font-bold text-[#51463d] flex items-center gap-1.5">
              <Crop size={14} className="text-[#9D4C29]" />
              <span>Aspect Ratio:</span>
            </span>
            <div className="flex flex-wrap gap-1.5">
              {ASPECT_RATIOS.map((r) => {
                const active = aspectRatio === r.value
                return (
                  <button
                    key={r.label}
                    type="button"
                    onClick={() => {
                      setAspectRatio(r.value)
                      setPan({ x: 0, y: 0 })
                    }}
                    className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition cursor-pointer ${
                      active
                        ? 'bg-[#9D4C29] text-white shadow-xs'
                        : 'bg-white border border-orange-100 text-[#51463d] hover:bg-orange-50'
                    }`}
                  >
                    {r.label}
                  </button>
                )
              })}
            </div>
          </div>

          {/* Zoom & Rotation Controls Bar */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 p-3.5 rounded-xl bg-white border border-orange-100">
            {/* Zoom Slider */}
            <div className="flex items-center gap-3">
              <span className="text-xs font-semibold text-[#51463d] shrink-0">Zoom:</span>
              <button
                type="button"
                onClick={() => handleZoomChange(zoom - 0.1)}
                className="p-1 rounded-md text-gray-500 hover:bg-orange-50 hover:text-[#9D4C29] transition cursor-pointer"
                title="Zoom Out"
              >
                <ZoomOut size={16} />
              </button>
              <input
                type="range"
                min="1"
                max="3"
                step="0.05"
                value={zoom}
                onChange={(e) => handleZoomChange(parseFloat(e.target.value))}
                className="flex-1 accent-[#9D4C29] cursor-pointer"
              />
              <button
                type="button"
                onClick={() => handleZoomChange(zoom + 0.1)}
                className="p-1 rounded-md text-gray-500 hover:bg-orange-50 hover:text-[#9D4C29] transition cursor-pointer"
                title="Zoom In"
              >
                <ZoomIn size={16} />
              </button>
              <span className="text-xs font-mono font-bold text-[#9D4C29] w-9 text-right">
                {zoom.toFixed(1)}x
              </span>
            </div>

            {/* Rotation & Reset Actions */}
            <div className="flex items-center justify-between sm:justify-end gap-2 border-t sm:border-t-0 border-orange-50 pt-2 sm:pt-0">
              <button
                type="button"
                onClick={() => handleRotate(90)}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-orange-100 bg-[#FFFCF9] text-xs font-semibold text-[#51463d] hover:bg-orange-50 transition cursor-pointer"
                title="Rotate 90 degrees clockwise"
              >
                <RotateCw size={13} className="text-[#9D4C29]" />
                <span>Rotate 90°</span>
              </button>

              <button
                type="button"
                onClick={handleReset}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-orange-100 bg-[#FFFCF9] text-xs font-semibold text-[#51463d] hover:bg-orange-50 transition cursor-pointer"
                title="Reset zoom and rotation"
              >
                <RefreshCw size={13} className="text-[#9D4C29]" />
                <span>Reset</span>
              </button>

              <button
                type="button"
                onClick={() => setShowLivePreview((prev) => !prev)}
                className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-xs font-semibold transition cursor-pointer ${
                  showLivePreview
                    ? 'border-[#9D4C29] bg-[#FFF0E7] text-[#9D4C29]'
                    : 'border-orange-100 bg-[#FFFCF9] text-[#51463d] hover:bg-orange-50'
                }`}
                title="Toggle live preview"
              >
                <Eye size={13} />
                <span>Preview</span>
              </button>
            </div>
          </div>

          {/* Live Preview Dropdown Section */}
          {showLivePreview && (
            <div className="p-3.5 rounded-xl border border-orange-200 bg-[#FFF0E7]/40 flex flex-col sm:flex-row items-center gap-4">
              <div className="h-28 w-36 rounded-lg overflow-hidden border border-orange-200 bg-white shadow-xs shrink-0 flex items-center justify-center">
                {livePreviewUrl ? (
                  <img
                    src={livePreviewUrl}
                    alt="Cropped Preview"
                    className="w-full h-full object-cover"
                  />
                ) : (
                  <span className="text-[11px] text-gray-400">Rendering...</span>
                )}
              </div>
              <div className="text-xs text-[#7A675D] space-y-1">
                <p className="font-bold text-[#302820]">Live Cropped Output Preview</p>
                <p>
                  Dimensions will be standardized to high-definition 1200×900 max pixels with sharp
                  smoothing upon confirmation.
                </p>
                <p className="text-[11px] text-emerald-700 font-semibold">
                  ✓ High-quality JPEG export (92% quality, optimized for mobile & desktop)
                </p>
              </div>
            </div>
          )}
        </div>

        {/* Modal Footer */}
        <div className="flex flex-col sm:flex-row items-center justify-between gap-3 border-t border-orange-100 bg-white px-5 py-3.5">
          <button
            type="button"
            onClick={onClose}
            className="w-full sm:w-auto rounded-xl border border-orange-200 bg-white px-4 py-2 text-xs font-semibold text-[#51463d] hover:bg-gray-50 transition cursor-pointer"
          >
            Cancel
          </button>

          <div className="flex items-center gap-2.5 w-full sm:w-auto">
            <button
              type="button"
              onClick={onSkip}
              className="flex-1 sm:flex-initial rounded-xl border border-orange-200 bg-white px-4 py-2 text-xs font-semibold text-[#8B776D] hover:bg-orange-50 transition cursor-pointer"
              title="Use original uncropped image"
            >
              Skip Crop
            </button>

            <button
              type="button"
              disabled={isProcessing}
              onClick={handleApply}
              className="flex-1 sm:flex-initial inline-flex items-center justify-center gap-1.5 rounded-xl bg-[#9D4C29] px-5 py-2 text-xs font-bold text-white shadow-xs hover:bg-[#813d21] disabled:opacity-50 transition cursor-pointer"
            >
              <Check size={14} />
              <span>
                {isProcessing
                  ? 'Processing…'
                  : isLast
                  ? 'Apply & Finish'
                  : 'Apply & Next Image'}
              </span>
              {!isLast && <ArrowRight size={13} />}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
