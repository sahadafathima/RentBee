from rest_framework.routers import DefaultRouter
from.views import Studentsviewset

router=DefaultRouter()
router.register('students',Studentsviewset)
urlpatterns = router.urls

