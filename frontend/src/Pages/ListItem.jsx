import { useState, useEffect, useRef } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  Upload,
  Star,
  Crop,
  RefreshCw,
  Trash2,
  Plus,
  CheckCircle2,
  AlertCircle,
  Sparkles,
} from 'lucide-react'
import Navbar from '../Components/Navbar'
import Footer from '../Components/Footer'
import ImageCropModal from '../Components/ImageCropModal'
import { getPublicCategories, createItem } from '../services/api'

export default function ListItem() {
  const navigate = useNavigate()

  // Categories list
  const [categories, setCategories] = useState([])
  const [loadingCategories, setLoadingCategories] = useState(true)

  // Form State
  const [form, setForm] = useState({
    name: '',
    categoryId: '',
    rentalPrice: '',
    stock: 1,
    deposit: '',
    description: '',
  })

  // Images state
  const [files, setFiles] = useState([])
  const [previews, setPreviews] = useState([])
  const [primaryIndex, setPrimaryIndex] = useState(0)
  const objectUrlsRef = useRef([])

  // Crop modal state
  const [cropModalData, setCropModalData] = useState(null)
  const replaceIndexRef = useRef(null)
  const replaceFileInputRef = useRef(null)

  // Rental kit accessory list
  const [rentalKit, setRentalKit] = useState([])

  // Submission & UI feedback state
  const [submitting, setSubmitting] = useState(false)
  const [errorMessage, setErrorMessage] = useState('')
  const [successMessage, setSuccessMessage] = useState('')

  // Load active categories on mount
  useEffect(() => {
    let isCurrent = true
    getPublicCategories()
      .then((data) => {
        if (!isCurrent) return
        const list = Array.isArray(data) ? data : []
        setCategories(list)
        if (list.length > 0) {
          setForm((prev) => ({
            ...prev,
            categoryId: prev.categoryId || String(list[0].id),
          }))
        }
      })
      .catch((err) => {
        if (!isCurrent) return
        console.error('Failed to load categories:', err)
        setErrorMessage('Failed to load categories. Please refresh the page.')
      })
      .finally(() => {
        if (isCurrent) setLoadingCategories(false)
      })

    return () => {
      isCurrent = false
    }
  }, [])

  // Clean up object URLs on unmount
  useEffect(() => {
    return () => {
      objectUrlsRef.current.forEach((url) => {
        try {
          URL.revokeObjectURL(url)
        } catch {
          // ignore
        }
      })
      objectUrlsRef.current = []
    }
  }, [])

  // Handle new files selected from file picker
  const handleFileSelect = (e) => {
    const selected = Array.from(e.target.files || [])
    if (!selected.length) return
    setCropModalData({ files: selected, type: 'new' })
    e.target.value = ''
  }

  // Trigger file replacement for a specific thumbnail
  const handleTriggerReplace = (idx) => {
    replaceIndexRef.current = idx
    if (replaceFileInputRef.current) {
      replaceFileInputRef.current.value = ''
      replaceFileInputRef.current.click()
    }
  }

  // Handle re-cropping an already selected image
  const handleRecrop = (idx) => {
    const targetFile = files[idx]
    if (!targetFile) return
    setCropModalData({ files: [targetFile], type: 'recrop', replaceIndex: idx })
  }

  // Handle file selected from replace input
  const handleReplaceFileChange = (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    setCropModalData({
      files: [file],
      type: 'recrop',
      replaceIndex: replaceIndexRef.current,
    })
    e.target.value = ''
  }

  // Handle crop completion
  const handleCropComplete = (croppedFiles) => {
    if (!croppedFiles || !croppedFiles.length) {
      setCropModalData(null)
      return
    }

    if (cropModalData?.type === 'recrop' && cropModalData.replaceIndex !== undefined) {
      const idx = cropModalData.replaceIndex
      const updatedFile = croppedFiles[0]
      const oldUrl = previews[idx]
      if (oldUrl) {
        try {
          URL.revokeObjectURL(oldUrl)
        } catch {
          // ignore
        }
      }
      const newUrl = URL.createObjectURL(updatedFile)
      objectUrlsRef.current.push(newUrl)

      setFiles((prev) => prev.map((f, i) => (i === idx ? updatedFile : f)))
      setPreviews((prev) => prev.map((u, i) => (i === idx ? newUrl : u)))
    } else {
      // Append newly cropped files
      const newUrls = croppedFiles.map((f) => URL.createObjectURL(f))
      objectUrlsRef.current.push(...newUrls)
      setFiles((prev) => [...prev, ...croppedFiles])
      setPreviews((prev) => [...prev, ...newUrls])
    }

    setCropModalData(null)
    setErrorMessage('')
  }

  // Remove an image preview
  const handleRemoveImage = (idx) => {
    const targetUrl = previews[idx]
    if (targetUrl) {
      try {
        URL.revokeObjectURL(targetUrl)
      } catch {
        // ignore
      }
      objectUrlsRef.current = objectUrlsRef.current.filter((u) => u !== targetUrl)
    }

    setFiles((prev) => prev.filter((_, i) => i !== idx))
    setPreviews((prev) => prev.filter((_, i) => i !== idx))

    if (primaryIndex === idx) {
      setPrimaryIndex(0)
    } else if (primaryIndex > idx) {
      setPrimaryIndex((p) => Math.max(0, p - 1))
    }
  }

  // Rental kit accessory handlers
  const handleAddRentalKitEntry = () => {
    setRentalKit((prev) => [...prev, ''])
  }

  const handleUpdateRentalKitEntry = (index, value) => {
    setRentalKit((prev) => prev.map((entry, idx) => (idx === index ? value : entry)))
  }

  const handleRemoveRentalKitEntry = (index) => {
    setRentalKit((prev) => prev.filter((_, idx) => idx !== index))
  }

  // Form submit handler
  const handleSubmit = async (e) => {
    e.preventDefault()
    setErrorMessage('')

    // Validations
    if (!form.name.trim()) {
      setErrorMessage('Please provide an item name.')
      return
    }

    if (!form.categoryId) {
      setErrorMessage('Please select a category.')
      return
    }

    const price = parseFloat(form.rentalPrice)
    if (isNaN(price) || price <= 0) {
      setErrorMessage('Please enter a valid daily rental price greater than ₹0.')
      return
    }

    const stock = parseInt(form.stock, 10)
    if (isNaN(stock) || stock < 1) {
      setErrorMessage('Available stock must be at least 1.')
      return
    }

    if (files.length === 0) {
      setErrorMessage('Please upload at least one image of your item.')
      return
    }

    setSubmitting(true)

    try {
      const fd = new FormData()
      fd.append('name', form.name.trim())
      fd.append('category_id', form.categoryId)
      fd.append('rental_price', price.toFixed(2))
      fd.append('stock', String(stock))

      const depositVal = String(form.deposit ?? '').trim()
      fd.append('deposit', depositVal ? parseFloat(depositVal).toFixed(2) : '0.00')

      fd.append('description', form.description.trim())
      fd.append('is_published', 'true')

      // Rental kit entries
      const cleanedRentalKit = rentalKit.map((s) => s.trim()).filter(Boolean)
      fd.append('rental_kit', JSON.stringify(cleanedRentalKit))

      // Images and primary cover index
      files.forEach((f) => fd.append('images', f))
      fd.append('primary_image_index', String(primaryIndex))

      const created = await createItem(fd)
      setSuccessMessage('Item listed successfully! Redirecting...')

      setTimeout(() => {
        if (created?.id) {
          navigate(`/items/${created.id}`)
        } else {
          navigate('/host-hub')
        }
      }, 1200)
    } catch (err) {
      console.error('Failed to create item listing:', err)
      setErrorMessage(
        err.message || 'Failed to list item. Please check the details and try again.'
      )
      setSubmitting(false)
    }
  }

  return (
    <div className="min-h-screen bg-[#FFFCF9] flex flex-col justify-between">
      <div>
        <Navbar />

        <main className="mx-auto max-w-4xl px-4 py-8 sm:px-6 lg:px-8">
          
          {/* Breadcrumb Navigation */}
          <nav className="mb-4 flex items-center gap-2 text-xs text-gray-500">
            <Link to="/" className="hover:text-[#D97745] transition">
              Home
            </Link>
            <span>/</span>
            <span className="font-semibold text-[#352720]">List an Item</span>
          </nav>

          {/* Page Header */}
          <div className="mb-8">
            <div className="inline-flex items-center gap-1.5 rounded-full bg-[#FFF0E7] px-3 py-1 text-xs font-bold text-[#D97745] mb-2">
              <Sparkles size={13} />
              <span>Earn With Your Gear</span>
            </div>
            <h1 className="text-2xl font-black text-[#352720] sm:text-3xl">
              List an Item for Rent
            </h1>
            <p className="mt-1 text-xs text-gray-500 sm:text-sm max-w-2xl leading-relaxed">
              Turn your unused items into extra income. Share your gear safely with verified neighbors and manage incoming requests in Request Details.
            </p>
          </div>

          {/* Error Banner */}
          {errorMessage && (
            <div className="mb-6 flex items-start gap-2.5 rounded-2xl bg-rose-50 border border-rose-200 p-4 text-xs font-semibold text-rose-800 animate-in fade-in">
              <AlertCircle size={16} className="text-rose-600 shrink-0 mt-0.5" />
              <span>{errorMessage}</span>
            </div>
          )}

          {/* Success Banner */}
          {successMessage && (
            <div className="mb-6 flex items-center gap-2 rounded-2xl bg-emerald-50 border border-emerald-200 p-4 text-xs font-semibold text-emerald-800 animate-in fade-in">
              <CheckCircle2 size={16} className="text-emerald-600 shrink-0" />
              <span>{successMessage}</span>
            </div>
          )}

          {/* Listing Form Card */}
          <div className="rounded-3xl border border-orange-100 bg-white p-6 sm:p-8 shadow-xs">
            <form onSubmit={handleSubmit} className="space-y-6">

              {/* Section 1: Basic Information */}
              <div>
                <h2 className="text-sm font-bold uppercase tracking-wider text-[#9D4C29] mb-3">
                  1. Basic Information
                </h2>
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                  <div className="sm:col-span-2">
                    <label className="block text-xs font-semibold text-[#51463d] mb-1.5">
                      Item Name <span className="text-rose-500">*</span>
                    </label>
                    <input
                      required
                      type="text"
                      maxLength={200}
                      value={form.name}
                      onChange={(e) => setForm({ ...form, name: e.target.value })}
                      placeholder="e.g. Sony Alpha A7 IV Mirrorless Camera"
                      className="w-full rounded-xl border border-orange-200 bg-white px-3.5 py-2.5 text-sm text-[#352720] placeholder-gray-400 outline-none focus:border-[#D97745] focus:ring-1 focus:ring-[#D97745] transition"
                    />
                  </div>

                  <div className="sm:col-span-2">
                    <label className="block text-xs font-semibold text-[#51463d] mb-1.5">
                      Category <span className="text-rose-500">*</span>
                    </label>
                    <select
                      required
                      value={form.categoryId}
                      onChange={(e) => setForm({ ...form, categoryId: e.target.value })}
                      disabled={loadingCategories}
                      className="w-full rounded-xl border border-orange-200 bg-white px-3.5 py-2.5 text-sm text-[#352720] outline-none focus:border-[#D97745] focus:ring-1 focus:ring-[#D97745] transition"
                    >
                      {loadingCategories ? (
                        <option value="">Loading categories...</option>
                      ) : categories.length === 0 ? (
                        <option value="">No categories available</option>
                      ) : (
                        categories.map((c) => (
                          <option key={c.id} value={c.id}>
                            {c.icon ? `${c.icon} ` : ''}{c.name}
                          </option>
                        ))
                      )}
                    </select>
                  </div>
                </div>
              </div>

              <div className="border-t border-orange-50 pt-5">
                {/* Section 2: Pricing & Inventory */}
                <h2 className="text-sm font-bold uppercase tracking-wider text-[#9D4C29] mb-3">
                  2. Pricing & Inventory
                </h2>
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
                  <div>
                    <label className="block text-xs font-semibold text-[#51463d] mb-1.5">
                      Daily Rental Price (₹) <span className="text-rose-500">*</span>
                    </label>
                    <div className="relative">
                      <span className="absolute left-3.5 top-2.5 text-sm text-gray-400 font-medium">₹</span>
                      <input
                        required
                        type="number"
                        step="0.01"
                        min="1"
                        value={form.rentalPrice}
                        onChange={(e) => setForm({ ...form, rentalPrice: e.target.value })}
                        placeholder="e.g. 450"
                        className="w-full rounded-xl border border-orange-200 bg-white pl-8 pr-3.5 py-2.5 text-sm text-[#352720] placeholder-gray-400 outline-none focus:border-[#D97745] focus:ring-1 focus:ring-[#D97745] transition"
                      />
                    </div>
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-[#51463d] mb-1.5">
                      Security Deposit (₹) <span className="text-gray-400 font-normal">(optional)</span>
                    </label>
                    <div className="relative">
                      <span className="absolute left-3.5 top-2.5 text-sm text-gray-400 font-medium">₹</span>
                      <input
                        type="number"
                        step="0.01"
                        min="0"
                        value={form.deposit}
                        onChange={(e) => setForm({ ...form, deposit: e.target.value })}
                        placeholder="0.00"
                        className="w-full rounded-xl border border-orange-200 bg-white pl-8 pr-3.5 py-2.5 text-sm text-[#352720] placeholder-gray-400 outline-none focus:border-[#D97745] focus:ring-1 focus:ring-[#D97745] transition"
                      />
                    </div>
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-[#51463d] mb-1.5">
                      Stock Quantity <span className="text-rose-500">*</span>
                    </label>
                    <input
                      required
                      type="number"
                      min="1"
                      value={form.stock}
                      onChange={(e) => setForm({ ...form, stock: e.target.value })}
                      placeholder="1"
                      className="w-full rounded-xl border border-orange-200 bg-white px-3.5 py-2.5 text-sm text-[#352720] placeholder-gray-400 outline-none focus:border-[#D97745] focus:ring-1 focus:ring-[#D97745] transition"
                    />
                  </div>
                </div>
              </div>

              <div className="border-t border-orange-50 pt-5">
                {/* Section 3: Description */}
                <h2 className="text-sm font-bold uppercase tracking-wider text-[#9D4C29] mb-3">
                  3. Description & Details
                </h2>
                <div>
                  <label className="block text-xs font-semibold text-[#51463d] mb-1.5">
                    Description <span className="text-gray-400 font-normal">(optional)</span>
                  </label>
                  <textarea
                    rows={4}
                    value={form.description}
                    onChange={(e) => setForm({ ...form, description: e.target.value })}
                    placeholder="Describe item condition, key features, guidelines for renters, or special handling instructions..."
                    className="w-full rounded-xl border border-orange-200 bg-white px-3.5 py-2.5 text-sm text-[#352720] placeholder-gray-400 outline-none focus:border-[#D97745] focus:ring-1 focus:ring-[#D97745] transition resize-none"
                  />
                </div>
              </div>

              <div className="border-t border-orange-50 pt-5">
                {/* Section 4: Item Photos */}
                <div className="flex items-center justify-between mb-3">
                  <div>
                    <h2 className="text-sm font-bold uppercase tracking-wider text-[#9D4C29]">
                      4. Item Photos <span className="text-rose-500">*</span>
                    </h2>
                    <p className="text-xs text-gray-400">
                      Upload at least 1 photo. You can crop, resize, and choose a cover photo.
                    </p>
                  </div>
                  {files.length > 0 && (
                    <span className="text-xs font-semibold text-[#D97745]">
                      {files.length} {files.length === 1 ? 'photo' : 'photos'} added
                    </span>
                  )}
                </div>

                {/* Upload Trigger Area */}
                <label className="flex flex-col items-center justify-center gap-2 rounded-2xl border-2 border-dashed border-orange-200 bg-[#FFFDFB] p-6 hover:bg-orange-50/50 hover:border-[#D97745] transition cursor-pointer">
                  <div className="flex h-12 w-12 items-center justify-center rounded-full bg-orange-100 text-[#D97745]">
                    <Upload size={22} />
                  </div>
                  <div className="text-center">
                    <span className="text-sm font-bold text-[#352720]">Click to upload photos</span>
                    <p className="text-xs text-gray-400 mt-0.5">JPG, PNG, WebP up to 10MB each</p>
                  </div>
                  <input
                    type="file"
                    multiple
                    accept="image/*"
                    onChange={handleFileSelect}
                    className="hidden"
                  />
                </label>

                {/* Hidden input for replacing a single photo */}
                <input
                  ref={replaceFileInputRef}
                  type="file"
                  accept="image/*"
                  onChange={handleReplaceFileChange}
                  className="hidden"
                />

                {/* Image Previews Grid */}
                {previews.length > 0 && (
                  <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
                    {previews.map((previewUrl, idx) => {
                      const isCover = primaryIndex === idx
                      return (
                        <div
                          key={idx}
                          className={`group relative overflow-hidden rounded-2xl border-2 bg-gray-50 aspect-4/3 ${
                            isCover ? 'border-[#D97745] shadow-xs' : 'border-gray-200'
                          }`}
                        >
                          <img
                            src={previewUrl}
                            alt={`Preview ${idx + 1}`}
                            className="h-full w-full object-cover"
                          />

                          {/* Cover Badge */}
                          {isCover && (
                            <span className="absolute top-2 left-2 flex items-center gap-1 rounded-md bg-[#D97745] px-2 py-0.5 text-[10px] font-bold text-white shadow-xs">
                              <Star size={10} fill="currentColor" /> Cover
                            </span>
                          )}

                          {/* Hover Action Overlay */}
                          <div className="absolute inset-0 flex flex-col justify-between bg-black/40 p-2 opacity-0 group-hover:opacity-100 transition">
                            <div className="flex justify-end gap-1.5">
                              {/* Re-crop Button */}
                              <button
                                type="button"
                                onClick={() => handleRecrop(idx)}
                                title="Crop / Resize"
                                className="flex h-7 w-7 items-center justify-center rounded-lg bg-white/90 text-gray-700 hover:bg-white transition cursor-pointer"
                              >
                                <Crop size={14} />
                              </button>

                              {/* Replace Button */}
                              <button
                                type="button"
                                onClick={() => handleTriggerReplace(idx)}
                                title="Replace photo"
                                className="flex h-7 w-7 items-center justify-center rounded-lg bg-white/90 text-gray-700 hover:bg-white transition cursor-pointer"
                              >
                                <RefreshCw size={14} />
                              </button>

                              {/* Delete Button */}
                              <button
                                type="button"
                                onClick={() => handleRemoveImage(idx)}
                                title="Remove photo"
                                className="flex h-7 w-7 items-center justify-center rounded-lg bg-rose-600 text-white hover:bg-rose-700 transition cursor-pointer"
                              >
                                <Trash2 size={14} />
                              </button>
                            </div>

                            {/* Set Cover Button */}
                            {!isCover && (
                              <button
                                type="button"
                                onClick={() => setPrimaryIndex(idx)}
                                className="w-full rounded-lg bg-white/90 py-1 text-[11px] font-bold text-[#352720] hover:bg-white transition flex items-center justify-center gap-1 cursor-pointer"
                              >
                                <Star size={12} /> Set as Cover
                              </button>
                            )}
                          </div>
                        </div>
                      )
                    })}
                  </div>
                )}
              </div>

              <div className="border-t border-orange-50 pt-5">
                {/* Section 5: Rental Kit (Optional) */}
                <div className="flex items-center justify-between mb-2">
                  <div>
                    <h2 className="text-sm font-bold uppercase tracking-wider text-[#9D4C29]">
                      5. What&apos;s Included in the Rental Kit? <span className="text-gray-400 font-normal">(optional)</span>
                    </h2>
                    <p className="text-xs text-gray-400">
                      Add accessories bundled with this item (e.g. Carry Case, 64GB SD Card, Extra Battery).
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={handleAddRentalKitEntry}
                    className="inline-flex items-center gap-1 rounded-xl bg-orange-50 border border-orange-200 px-3 py-1.5 text-xs font-bold text-[#D97745] hover:bg-orange-100 transition cursor-pointer"
                  >
                    <Plus size={14} /> Add Accessory
                  </button>
                </div>

                {rentalKit.length === 0 ? (
                  <div className="rounded-2xl border border-dashed border-orange-100 bg-[#FFFDFB] p-4 text-center text-xs text-gray-400">
                    No accessories added yet. Click &quot;+ Add Accessory&quot; if this item includes extra gear.
                  </div>
                ) : (
                  <div className="space-y-2 mt-3">
                    {rentalKit.map((item, idx) => (
                      <div key={idx} className="flex items-center gap-2">
                        <input
                          type="text"
                          value={item}
                          onChange={(e) => handleUpdateRentalKitEntry(idx, e.target.value)}
                          placeholder="e.g. Battery Charger & 1x Battery"
                          className="flex-1 rounded-xl border border-orange-200 bg-white px-3.5 py-2 text-sm text-[#352720] placeholder-gray-400 outline-none focus:border-[#D97745] focus:ring-1 focus:ring-[#D97745] transition"
                        />
                        <button
                          type="button"
                          onClick={() => handleRemoveRentalKitEntry(idx)}
                          title="Remove accessory"
                          className="flex h-9 w-9 items-center justify-center rounded-xl border border-rose-200 bg-rose-50 text-rose-600 hover:bg-rose-100 transition cursor-pointer"
                        >
                          <Trash2 size={15} />
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Action Buttons */}
              <div className="border-t border-orange-100 pt-6 flex flex-col-reverse gap-3 sm:flex-row sm:items-center sm:justify-end">
                <button
                  type="button"
                  onClick={() => navigate(-1)}
                  disabled={submitting}
                  className="rounded-full border border-orange-200 bg-white px-6 py-3 text-sm font-bold text-[#49362D] hover:bg-orange-50 transition text-center cursor-pointer"
                >
                  Cancel
                </button>

                <button
                  type="submit"
                  disabled={submitting}
                  className="rounded-full bg-[#D97745] px-8 py-3 text-sm font-bold text-white shadow-xs hover:bg-[#B85D32] transition flex items-center justify-center gap-2 cursor-pointer disabled:opacity-60 disabled:cursor-not-allowed"
                >
                  {submitting ? (
                    <>
                      <div className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
                      <span>Creating Listing...</span>
                    </>
                  ) : (
                    <span>+ List Your Item</span>
                  )}
                </button>
              </div>

            </form>
          </div>

        </main>
      </div>

      {/* Image Crop Modal */}
      {cropModalData && (
        <ImageCropModal
          files={cropModalData.files}
          onComplete={handleCropComplete}
          onClose={() => setCropModalData(null)}
        />
      )}

      <Footer />
    </div>
  )
}
