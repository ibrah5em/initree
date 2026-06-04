package main

import (
	"log"

	"github.com/gin-gonic/gin"

	"${project.slug}/internal/handler"
)

func main() {
	r := gin.Default()
	handler.Register(r)

	if err := r.Run(":${app.port}"); err != nil {
		log.Fatal(err)
	}
}
