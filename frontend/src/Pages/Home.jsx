import { useState } from 'react'
import Navbar from '../Components/Navbar'
import HeroSection from '../Components/HeroSection'
import BrowseCategories from '../Components/BrowseCategories'
import PopularRentals from '../Components/PopularRentals'
import HowItWorks from '../Components/HowItWorks'
import ListItemBanner from '../Components/ListItemBanner'
import Footer from '../Components/Footer'
import BookingNotifications from '../Components/BookingNotifications'

function Home() {
  const [selectedCategory, setSelectedCategory] = useState('')

  return (
    <div className="min-h-screen bg-[#FFFCF9]">
      <Navbar />
      <main>
        <BookingNotifications />
        <HeroSection />
        <BrowseCategories
          selectedCategory={selectedCategory}
          onSelectCategory={setSelectedCategory}
        />
        <PopularRentals selectedCategory={selectedCategory} />
        <HowItWorks />
        <ListItemBanner />
      </main>
      <Footer />
    </div>
  )
}

export default Home
