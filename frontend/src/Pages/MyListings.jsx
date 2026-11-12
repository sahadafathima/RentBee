import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import Navbar from '../Components/Navbar'
import Footer from '../Components/Footer'
import { ItemModal } from './AdminItemManagement'
import { getMyListings, getMyListing, getPublicCategories, updateMyListing, deactivateMyListing } from '../services/api'

export function ListingActions({ item, disabled, onEdit }) {
  return <div className="grid w-full grid-cols-2 gap-3">
    <Link to={`/items/${item.id}?preview=owner`} className="inline-flex items-center justify-center rounded-full border border-orange-200 bg-orange-50 px-4 py-2.5 font-semibold hover:bg-orange-100">View</Link>
    <button type="button" disabled={disabled} onClick={() => onEdit(item.id)} className="rounded-full bg-[#9D4C29] px-4 py-2.5 font-semibold text-white hover:bg-[#813B20] disabled:opacity-50">Edit</button>
  </div>
}

export default function MyListings() {
  const [items, setItems] = useState([])
  const [categories, setCategories] = useState([])
  const [revision, setRevision] = useState(0)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [opening, setOpening] = useState(false)
  const [failedImages, setFailedImages] = useState([])
  const [modal, setModal] = useState(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  useEffect(() => {
    let active = true
    Promise.allSettled([getMyListings(), getPublicCategories()]).then(([listings, cats]) => {
      if (!active) return
      const errors = []
      if (listings.status === 'fulfilled' && Array.isArray(listings.value.results)) setItems(listings.value.results)
      else errors.push(listings.reason?.message || 'Could not load listings.')
      if (cats.status === 'fulfilled' && Array.isArray(cats.value)) setCategories(cats.value)
      else errors.push('Categories could not be loaded. You can retain the current category; retry to change it.')
      setError(errors.join(' '))
    }).catch((err) => { if (active) setError(err.message) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [revision])
  const openEdit = async (id) => {
    setOpening(true); setError(''); setNotice('')
    try {
      const item = await getMyListing(id)
      setModal({ mode: 'edit', item })
    } catch (err) { setError(err.message || 'Could not open this listing.') }
    finally { setOpening(false) }
  }
  const save = async (formData, id) => {
    setSaving(true); setError('')
    try {
      const updated = await updateMyListing(id, formData)
      setItems((current) => current.map((item) => item.id === updated.id ? updated : item))
      setFailedImages((ids) => ids.filter((failedId) => failedId !== updated.id))
      setModal(null); setNotice('Listing updated.'); setRevision((v) => v + 1)
    } catch (err) { setError(err.message) }
    finally { setSaving(false) }
  }
  const deactivate = async (item) => {
    if (!window.confirm(`Deactivate "${item.name}"? Booking history and reservations will be preserved.`)) return
    setSaving(true)
    try {
      await deactivateMyListing(item.id)
      setNotice('Listing deactivated. Existing bookings remain in Request Details.')
      setRevision((v) => v + 1)
    } catch (err) { setError(err.message) }
    finally { setSaving(false) }
  }
  return <div className="min-h-screen bg-[#FFFCF9]"><Navbar />
    <main className="mx-auto max-w-6xl p-4 sm:p-8">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold text-[#49362D]">My Listings</h1>
        <div className="flex gap-4 text-sm text-[#9D4C29]"><Link to="/list-item">List an Item</Link><Link to="/host-hub">Incoming Requests</Link><Link to="/bookings">My Bookings</Link></div>
      </div>
      {error && <p role="alert" className="mb-4 rounded-xl bg-rose-50 p-4 text-rose-800">{error}<button onClick={() => setRevision((v) => v + 1)} className="ml-3 underline">Retry</button></p>}
      {notice && <p role="status" className="mb-4 rounded-xl bg-emerald-50 p-4 text-emerald-800">{notice}</p>}
      {loading ? <p>Loading listings...</p> : items.length === 0 && !error ? <p>You have no listings yet.</p> :
        <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">{items.map((item) =>
          <article key={item.id} className="rounded-2xl border border-orange-100 bg-white p-4">
            {item.primary_image_url && !failedImages.includes(item.id)
              ? <img src={item.primary_image_url} alt={item.name} onError={() => setFailedImages((ids) => [...ids, item.id])} className="mb-3 h-40 w-full rounded-xl object-cover" />
              : <div className="mb-3 flex h-40 items-center justify-center rounded-xl bg-orange-50 text-sm text-gray-500">No image available</div>}
            <p className="text-xs text-gray-500">{item.category_name} | {item.is_published ? 'Published' : 'Unpublished'}</p>
            <h2 className="mt-1 text-lg font-bold">{item.name}</h2><p className="line-clamp-2 text-sm text-gray-600">{item.description}</p>
            <p className="mt-3 text-sm">INR {item.rental_price}/day | Total stock: {item.total_stock}</p>
            <p className="text-sm">Available today: {item.available_stock ?? 'Unknown'} | {item.availability_reason?.replaceAll('_', ' ') || 'Availability unknown'}</p>
            {item.booking_activity && <p className="mt-2 text-xs text-gray-500">Incoming: {item.booking_activity.pending_approval || 0} | Active: {(item.booking_activity.waiting_for_pickup || 0) + (item.booking_activity.rental_in_progress || 0)}</p>}
            <div className="mt-4 flex flex-wrap gap-3 text-sm text-[#9D4C29]">
              <ListingActions item={item} disabled={saving || opening} onEdit={openEdit} />
              <button disabled={saving} onClick={() => deactivate(item)}>Deactivate</button>
              <Link to={`/host-hub?item=${item.id}`}>View booking requests</Link>
            </div>
          </article>)}</div>}
      {opening && <p role="status" className="mt-4 text-sm text-gray-600">Loading listing for editing...</p>}
      {modal && <ItemModal key={modal.item.id} stockLabel="Total stock" mode={modal.mode} item={modal.item} categories={categories} loading={saving} error={error} onClose={() => !saving && setModal(null)} onSave={save} />}
    </main><Footer /></div>
}
