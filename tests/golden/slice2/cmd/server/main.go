package main

import (
	"log"

	"github.com/gin-gonic/gin"

	"myapp/internal/handler"
)

func main() {
	r := gin.Default()
	handler.Register(r)

	if err := r.Run(":8080"); err != nil {
		log.Fatal(err)
	}
}
