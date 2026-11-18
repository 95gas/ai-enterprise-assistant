async function getUsage() {
  const response = await fetch('/api/general/v0/user_token', {
    method: 'GET',
    credentials: 'same-origin'
  })

  // TODO: handle errors
  return await response.json()
}

export { getUsage }