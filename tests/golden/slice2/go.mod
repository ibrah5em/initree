module myapp

go 1.22

require (
    // >>> initree:inject runtime.dependencies
    github.com/gin-gonic/gin v1.10.0
    // <<< initree:inject runtime.dependencies
)
