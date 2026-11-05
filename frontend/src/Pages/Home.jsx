
import Navbar from '../Components/Navbar'
import HeroSection from '../Components/HeroSection'
import BrowseCategories from '../Components/BrowseCategories'
import PopularRentals from '../Components/PopularRentals'
import HowItWorks from '../Components/HowItWorks'
import ListItemBanner from '../Components/ListItemBanner'
import Footer from '../Components/Footer'

function Home() {
  return (
    <div className="min-h-screen bg-[#FFFCF9]">
      <Navbar />
      <main>
        <HeroSection />
        <BrowseCategories />
        <PopularRentals />
        <HowItWorks />
        <ListItemBanner />
      </main>
      <Footer />
    </div>
  )
}

export default Home
