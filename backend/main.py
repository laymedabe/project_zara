"""
Project Zara — FastAPI Main Application
==========================================
Entry point for the Landslide Early Warning System base station.

Serves:
- REST API for dashboard data
- WebSocket for real-time updates
- Static frontend files (fully offline)
- Background LoRa listener (simulator or real hardware)
"""

import asyncio
import os
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

from config import HOST, PORT, DEBUG, FRONTEND_DIR, RiskLevel, RISK_COLORS, DATA_DIR
from database import db
from websocket_manager import ws_manager
from alert_manager import alert_manager
from data_processor import extract_features, validate_reading
import risk_engine


# =============================================================================
# DETERMINE MODE & STATE
# =============================================================================
USE_SIMULATOR = os.environ.get("ZARA_MODE", "simulator").lower() == "simulator"
SYSTEM_PAUSED = False


# =============================================================================
# DATA PIPELINE — Called when new sensor data arrives
# =============================================================================
async def on_sensor_data(data: dict):
    """
    Main data pipeline — triggered by LoRa receiver or simulator.
    
    Flow: Validate → Store → Extract Features → Assess Risk → Alert → Broadcast
    """
    global SYSTEM_PAUSED
    if SYSTEM_PAUSED:
        return

    # 1. Validate
    is_valid, issues = validate_reading(data)
    if not is_valid:
        data["is_valid"] = 0
        await db.log("WARNING", "DataPipeline", f"Invalid reading: {', '.join(issues)}")

    # 2. Store raw reading
    reading_id = await db.insert_reading(data)
    data["id"] = reading_id

    # 3. Broadcast raw sensor data to dashboard
    await ws_manager.broadcast_sensor_data(data)

    if not is_valid:
        return

    # 4. Extract features
    features = await extract_features(data)

    # 5. Assess risk
    assessment = risk_engine.assess(features)
    assessment["reading_id"] = reading_id

    # 6. Store assessment
    assessment_id = await db.insert_assessment(assessment)
    assessment["id"] = assessment_id

    # 7. Broadcast risk update
    await ws_manager.broadcast_risk_update(assessment)

    # 8. Process alerts
    await alert_manager.process_risk_assessment(assessment)


# =============================================================================
# APP LIFECYCLE
# =============================================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage startup and shutdown."""
    # Startup
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    await db.connect()
    await db.log("INFO", "System", "Project Zara base station starting up")

    # Start LoRa listener in background
    if USE_SIMULATOR:
        from lora_simulator import LoRaSimulator
        receiver = LoRaSimulator()
        print("\n" + "=" * 60)
        print("  PROJECT ZARA -- SIMULATOR MODE")
        print("  Dashboard: http://localhost:8000")
        print("=" * 60 + "\n")
    else:
        from lora_receiver import LoRaReceiver
        receiver = LoRaReceiver()
        print("\n" + "=" * 60)
        print("  PROJECT ZARA -- LIVE LORA MODE")
        print("  Dashboard: http://localhost:8000")
        print("=" * 60 + "\n")

    receiver.on_data(on_sensor_data)

    async def _run_receiver():
        try:
            await receiver.start()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"[ERROR] LoRa/Simulator task failed: {e}", flush=True)
            import traceback
            traceback.print_exc()

    lora_task = asyncio.create_task(_run_receiver())

    yield

    # Shutdown
    await receiver.stop()
    lora_task.cancel()
    alert_manager.cleanup()
    await db.log("INFO", "System", "Project Zara base station shutting down")
    await db.close()


# =============================================================================
# FASTAPI APP
# =============================================================================
app = FastAPI(
    title="Project Zara — Landslide Early Warning System",
    description="Smart IoT-based landslide early warning for Leon, Iloilo",
    version="1.0.0",
    lifespan=lifespan,
)


# =============================================================================
# STATIC FILES (Frontend Dashboard)
# =============================================================================
# Serve index.html at root
@app.get("/", response_class=FileResponse)
async def serve_dashboard():
    return FileResponse(FRONTEND_DIR / "index.html")


# Serve all other static files
app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


# =============================================================================
# WEBSOCKET ENDPOINT
# =============================================================================
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        while True:
            # Keep connection alive, handle incoming messages
            data = await websocket.receive_text()
            # Client can send commands (e.g., acknowledge alert)
            # For now, we just keep the connection open
    except WebSocketDisconnect:
        await ws_manager.disconnect(websocket)


# =============================================================================
# REST API ENDPOINTS
# =============================================================================

# --- Dashboard Data ---
@app.get("/api/dashboard")
async def get_dashboard_data():
    """Get all data needed for initial dashboard render."""
    latest_reading = await db.get_latest_reading()
    latest_assessment = await db.get_latest_assessment()
    recent_alerts = await db.get_alerts(limit=20)
    stats = await db.get_stats()

    return {
        "latest_reading": latest_reading,
        "latest_assessment": latest_assessment,
        "recent_alerts": recent_alerts,
        "stats": stats,
        "risk_colors": {k.value: v for k, v in RISK_COLORS.items()},
        "mode": "simulator" if USE_SIMULATOR else "live",
        "system_paused": SYSTEM_PAUSED,
    }


# --- Sensor Readings ---
@app.get("/api/readings")
async def get_readings(hours: int = Query(default=24, ge=1, le=168)):
    """Get sensor readings for the last N hours (max 7 days)."""
    readings = await db.get_readings(hours=hours)
    return {"readings": readings, "count": len(readings)}


# --- Risk Assessments ---
@app.get("/api/assessments")
async def get_assessments(hours: int = Query(default=24, ge=1, le=168)):
    """Get risk assessments for the last N hours."""
    assessments = await db.get_assessments(hours=hours)
    return {"assessments": assessments, "count": len(assessments)}


# --- Rainfall Summary ---
@app.get("/api/rainfall")
async def get_rainfall_summary():
    """Get cumulative rainfall for all time windows."""
    return {
        "rainfall_1hr": round(await db.get_rainfall_sum(1), 2),
        "rainfall_3hr": round(await db.get_rainfall_sum(3), 2),
        "rainfall_24hr": round(await db.get_rainfall_sum(24), 2),
        "rainfall_72hr": round(await db.get_rainfall_sum(72), 2),
    }


# --- Alerts ---
@app.get("/api/alerts")
async def get_alerts(
    limit: int = Query(default=50, ge=1, le=200),
    unacknowledged_only: bool = Query(default=False),
):
    """Get recent alerts."""
    alerts = await db.get_alerts(limit=limit, unacknowledged_only=unacknowledged_only)
    return {"alerts": alerts, "count": len(alerts)}


@app.post("/api/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(alert_id: int):
    """Acknowledge an alert."""
    await db.acknowledge_alert(alert_id)
    return {"status": "ok", "alert_id": alert_id}


# --- System ---
@app.get("/api/system/stats")
async def get_system_stats():
    """Get system statistics."""
    stats = await db.get_stats()
    stats["ws_clients"] = ws_manager.client_count
    stats["mode"] = "simulator" if USE_SIMULATOR else "live"
    stats["system_paused"] = SYSTEM_PAUSED
    return stats

@app.post("/api/system/pause")
async def pause_system():
    global SYSTEM_PAUSED
    SYSTEM_PAUSED = True
    await db.log("INFO", "System", "Monitoring paused by admin.")
    return {"status": "ok", "system_paused": True}

@app.post("/api/system/resume")
async def resume_system():
    global SYSTEM_PAUSED
    SYSTEM_PAUSED = False
    await db.log("INFO", "System", "Monitoring resumed by admin.")
    return {"status": "ok", "system_paused": False}

@app.post("/api/system/clear-data")
async def clear_data():
    await db.clear_all_data()
    await db.log("INFO", "System", "All sensor data cleared by admin.")
    return {"status": "ok"}


# =============================================================================
# ENTRY POINT
# =============================================================================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=HOST,
        port=PORT,
        reload=DEBUG,
        log_level="info",
    )
