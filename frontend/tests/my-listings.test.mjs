import assert from 'node:assert/strict'
import { after, before, test } from 'node:test'
import { createServer } from 'vite'
import react from '@vitejs/plugin-react'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'

let server
let ListingActions
let ItemModal
before(async () => {
  server = await createServer({
    configFile: false,
    cacheDir: 'node_modules/.vite-owner-listing-tests',
    plugins: [react()],
    optimizeDeps: { noDiscovery: true, include: [] },
    server: { middlewareMode: true, watch: null },
    appType: 'custom',
  })
  ;({ ListingActions } = await server.ssrLoadModule('/src/Pages/MyListings.jsx'))
  ;({ ItemModal } = await server.ssrLoadModule('/src/Pages/AdminItemManagement.jsx'))
})
after(async () => { await server?.close() })

test('View links to the existing item details page with owner-scoped preview', () => {
  const html = renderToStaticMarkup(createElement(MemoryRouter, null,
    createElement(ListingActions, { item: { id: 42 }, onEdit() {} })))
  assert.match(html, /href="\/items\/42\?preview=owner"/)
  assert.match(html, />View<\/a>/)
  assert.match(html, />Edit<\/button>/)
})

test('Edit opens the shared editor for the exact listing ID', () => {
  const opened = []
  const actions = ListingActions({ item: { id: 73 }, disabled: false, onEdit: (id) => opened.push(id) })
  const edit = actions.props.children[1]
  assert.equal(edit.props.type, 'button')
  assert.equal(edit.props.disabled, false)
  edit.props.onClick()
  assert.deepEqual(opened, [73])
  assert.equal(ListingActions({ item: { id: 73 }, disabled: true }).props.children[1].props.disabled, true)
})

test('Shared edit form prefills existing fields and retains a retired category', () => {
  const html = renderToStaticMarkup(createElement(ItemModal, {
    mode: 'edit', categories: [], loading: false, onClose() {}, onSave() {},
    item: { id: 73, name: 'Original camera', description: 'Existing description',
      category_id: 9, category_name: 'Retired cameras', rental_price: '0.50',
      stock: 3, deposit: '20.00', is_published: true, rental_kit: ['Charger'],
      images: [{ id: 5, image: '/cover.jpg', is_primary: true }] },
  }))
  assert.match(html, /value="Original camera"/)
  assert.match(html, /Existing description/)
  assert.match(html, /value="9" selected=""/)
  assert.match(html, /Retired cameras \(current category\)/)
  assert.match(html, /min="0.01"[^>]*value="0.50"/)
  assert.match(html, /value="3"/)
  assert.match(html, /value="20.00"/)
  assert.match(html, /value="Charger"/)
  assert.match(html, /src="\/cover.jpg"/)
})

test('Rental-kit inputs show limits and counters and block oversized existing entries', () => {
  for (const length of [150, 151]) {
    const html = renderToStaticMarkup(createElement(ItemModal, {
      mode: 'edit', categories: [], loading: false, onClose() {}, onSave() {},
      item: { id: 73, name: 'Camera', rental_kit: ['X'.repeat(length), 'Charger'] },
    }))
    assert.match(html, /maxLength="150"/i)
    assert.ok(html.includes(`${length}/150`))
    assert.match(html, /7\/150/)
    assert.match(html, /Remove accessory/)
    assert.match(html, /Add Item/)
    if (length === 151) {
      assert.match(html, /Entry 1 exceeds 150 characters/)
      assert.match(html, /aria-invalid="true"/)
      assert.match(html, /type="submit" disabled=""/)
    } else {
      assert.doesNotMatch(html, /exceeds 150 characters/)
      assert.doesNotMatch(html, /type="submit" disabled=""/)
    }
  }
})
