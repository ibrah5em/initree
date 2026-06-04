package handler

import (
	"net/http"

	"github.com/gin-gonic/gin"
)

// Register wires the service routes onto r. The health route matches the path the rest of the
// stack reads from app.healthcheck_path, so the container and k8s probes hit the same endpoint.
func Register(r *gin.Engine) {
	r.GET("${app.healthcheck_path}", func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{"status": "ok"})
	})
}
