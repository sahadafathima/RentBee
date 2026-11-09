/**
 * Shared Rental Duration & Return Deadline Utilities
 * Timezone: Asia/Kolkata (IST)
 */

/**
 * Calculates rental duration based strictly on the difference between
 * the start date and return date (end_date - start_date).
 * Return date is NOT counted as an extra rental day.
 *
 * Examples:
 * - 9th to 10th = 1 day
 * - 9th to 11th = 2 days
 * - 9th to 12th = 3 days
 * - Same day or inverted = 0 days (invalid)
 */
export function calculateRentalDuration(startDateStr, endDateStr) {
  if (!startDateStr || !endDateStr) return 0
  const start = new Date(startDateStr + 'T00:00:00Z')
  const end = new Date(endDateStr + 'T00:00:00Z')
  if (isNaN(start.getTime()) || isNaN(end.getTime())) return 0

  const diffMs = end.getTime() - start.getTime()
  if (diffMs <= 0) return 0

  return Math.round(diffMs / (1000 * 60 * 60 * 24))
}

/**
 * Returns the calendar day immediately following the given YYYY-MM-DD string.
 * Used for setting min on return date pickers so return date must be at least 1 day after start date.
 */
export function getNextDayStr(dateStr) {
  if (!dateStr) return ''
  const d = new Date(dateStr + 'T00:00:00Z')
  if (isNaN(d.getTime())) return ''
  d.setUTCDate(d.getUTCDate() + 1)
  return d.toISOString().split('T')[0]
}

/**
 * Formats an ISO timestamp or Date object into human-readable Asia/Kolkata (IST) format.
 * Example output: "11 Nov 2026, 3:00 PM IST"
 */
export function formatKolkataDateTime(dateInput) {
  if (!dateInput) return ''
  const d = typeof dateInput === 'string' ? new Date(dateInput) : dateInput
  if (!d || isNaN(d.getTime())) return ''

  const formatted = d.toLocaleString('en-IN', {
    timeZone: 'Asia/Kolkata',
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
  })

  // Normalize formatting and append IST
  return `${formatted} IST`
}

/**
 * Calculates remaining or overdue countdown for a return deadline.
 * Returns breakdown and human-friendly status string.
 */
export function calculateReturnCountdown(deadlineInput) {
  if (!deadlineInput) {
    return {
      isValid: false,
      isOverdue: false,
      text: 'Pending pickup confirmation',
      days: 0,
      hours: 0,
      minutes: 0,
      seconds: 0,
    }
  }

  const deadline = typeof deadlineInput === 'string' ? new Date(deadlineInput) : deadlineInput
  if (isNaN(deadline.getTime())) {
    return {
      isValid: false,
      isOverdue: false,
      text: 'Invalid deadline',
      days: 0,
      hours: 0,
      minutes: 0,
      seconds: 0,
    }
  }

  const now = new Date()
  const diffMs = deadline.getTime() - now.getTime()

  if (diffMs <= 0) {
    const overdueMs = Math.abs(diffMs)
    const overdueHours = Math.floor(overdueMs / (1000 * 60 * 60))
    const overdueMins = Math.floor((overdueMs % (1000 * 60 * 60)) / (1000 * 60))

    let text
    if (overdueHours > 0) {
      text = `Deadline passed ${overdueHours}h ${overdueMins}m ago`
    } else if (overdueMins > 0) {
      text = `Deadline passed ${overdueMins}m ago`
    } else {
      text = 'Deadline passed just now'
    }

    return {
      isValid: true,
      isOverdue: true,
      text,
      days: 0,
      hours: overdueHours,
      minutes: overdueMins,
      seconds: Math.floor((overdueMs % (1000 * 60)) / 1000),
    }
  }

  const totalSeconds = Math.floor(diffMs / 1000)
  const days = Math.floor(totalSeconds / 86400)
  const hours = Math.floor((totalSeconds % 86400) / 3600)
  const minutes = Math.floor((totalSeconds % 3600) / 60)
  const seconds = totalSeconds % 60

  let text
  if (days > 0) {
    text = `${days}d ${hours}h ${minutes}m remaining`
  } else if (hours > 0) {
    text = `${hours}h ${minutes}m ${seconds}s remaining`
  } else {
    text = `${minutes}m ${seconds}s remaining`
  }

  return {
    isValid: true,
    isOverdue: false,
    text,
    days,
    hours,
    minutes,
    seconds,
  }
}
