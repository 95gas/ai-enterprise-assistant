import React from 'react'
import ReactDOM from 'react-dom/client'
import './index.css'
import {
  createBrowserRouter,
  RouterProvider,
} from "react-router-dom";
import AuthProvider from '@/components/providers/AuthProvider.tsx';
import ThemeProvider from '@/components/providers/ThemeProvider.tsx';
import LoginPage from './routes/login/LoginPage.tsx';
import { pdfjs } from 'react-pdf';
import AppRoute from './routes/App.tsx';
import SocketProvider from '@/components/providers/SocketProvider.tsx';
import { SidebarProvider } from './components/ui/sidebar.tsx';
import { I18nProvider } from "@lingui/react";
import { i18n } from "@lingui/core";
import { dynamicActivate } from "./i18n";

// import pdf worker
import src from 'pdfjs-dist/build/pdf.worker.min.mjs?worker&url';
pdfjs.GlobalWorkerOptions.workerSrc = src

// create router
const router = createBrowserRouter([
  AppRoute,
  {
    path: "/login",
    element: <LoginPage/>
  }
])

async function init() {
  // activate i18n
  await dynamicActivate(localStorage.getItem('vite-ui-locale') ?? import.meta.env.VITE_LOCALE)

  ReactDOM.createRoot(document.getElementById('root')!).render(
    <React.StrictMode>
      <ThemeProvider defaultTheme="dark" storageKey="vite-ui-theme">
        <I18nProvider i18n={i18n}>
          <SocketProvider>
            <AuthProvider>
              <SidebarProvider>
                <RouterProvider router={router} />
              </SidebarProvider>
            </AuthProvider>
          </SocketProvider>
        </I18nProvider>
      </ThemeProvider>
    </React.StrictMode>,
  )
}

init()