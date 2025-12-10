from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Import routers
from backend.auth.auth import router as auth_router
from backend.routers import convoy_routes, route_visualization

app = FastAPI(
    title="SmartConvoy AI (SARATHI)",
    description="Military Convoy Route Optimization System for Indian Army",
    version="1.0.0"
)

# ---------------------------------
# CORS (Allow React Frontend)
# ---------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------
# INCLUDE ALL ROUTERS
# ---------------------------------
app.include_router(auth_router, prefix="/api/auth", tags=["Authentication"])
app.include_router(convoy_routes.router, prefix="/api/convoys", tags=["Convoy Management"])
app.include_router(route_visualization.router, prefix="/api/routes", tags=["Route Visualization"])

# ---------------------------------
# DEFAULT ROOT ROUTE
# ---------------------------------
@app.get("/")
def root():
    return {
        "service": "SmartConvoy AI (SARATHI)",
        "version": "1.0.0",
        "status": "operational",
        "features": [
            "User authentication (Login/Register)",
            "Multi-convoy coordination",
            "Dynamic route optimization",
            "Risk zone detection",
            "Merge recommendations",
            "Real-time ETA prediction",
            "Live map visualization"
        ]
    }

# ---------------------------------
# HEALTH CHECK
# ---------------------------------
@app.get("/health")
def health_check():
    return {"status": "healthy", "service": "SmartConvoy AI"}

# ---------------------------------
# RUN UVICORN
# ---------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
