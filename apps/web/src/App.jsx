import React from "react";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import FoodPage from "./pages/FoodPage";
import StallPage from "./pages/StallPage";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<FoodPage />} />
        <Route path="/stall/:id" element={<StallPage />} />
      </Routes>
    </BrowserRouter>
  );
}