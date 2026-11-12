import Navbar from '../Components/Navbar'
import Footer from '../Components/Footer'
import BookingNotifications from '../Components/BookingNotifications'

export default function Notifications() {
  return <div className="min-h-screen bg-[#FFFCF9]"><Navbar /><main><BookingNotifications history /></main><Footer /></div>
}
