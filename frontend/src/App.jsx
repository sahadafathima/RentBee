import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'

import Home from './Pages/Home'
import Signup from './Pages/Signup'
import Login from './Pages/Login'
import ForgetPassword from './Pages/ForgetPassword'
import ResetPassword from './Pages/ResetPassword'
import AdminLogin from './Pages/AdminLogin'
import Profile from './Pages/Profile'
import EditProfile from './Pages/EditProfile'
import MyAddress from './Pages/MyAddress'
import UserManagement from './Pages/UserManagement'
import AdminCategoryManagement from './Pages/AdminCategoryManagement';
import AdminItemManagement from './Pages/AdminItemManagement';

import ProtectedAdminRoute from './Components/ProtectedAdminRoute'

function App() {
  return (
    <BrowserRouter>       
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/signup" element={<Signup />} />
        <Route path="/login" element={<Login />} />
        <Route path="/forget-password" element={<ForgetPassword />} />
        <Route path="/reset-password" element={<ResetPassword />} />
        <Route path="/admin/login" element={<AdminLogin />} />

        <Route path="/profile" element={<Profile />} />
        <Route path="/edit-profile" element={<EditProfile />} />
        <Route path="/my-address" element={<MyAddress />} />

        {/* Protected Admin Routes */}
        <Route element={<ProtectedAdminRoute />}>
          <Route
            path="/admin/users"
            element={<UserManagement />}
          />
          <Route
            path="/admin/categories"
            element={<AdminCategoryManagement />}
          />
          <Route
            path="/admin/items"
            element={<AdminItemManagement />}
          />
        </Route>

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}

export default App