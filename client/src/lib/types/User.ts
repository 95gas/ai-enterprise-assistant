export type User = {
  id: string
  email: string
  name: string
  groups: string[]
  domain: string
  permissions: {
    web_search: boolean
    doc_search: boolean
    upload_common: boolean
    upload_private: boolean
    app_name: boolean
  }
  last_login: string
  tot_token_limit: number
  tot_limit_reset_period: string
  expiring_date_trial: string
}