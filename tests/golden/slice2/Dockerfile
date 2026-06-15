# syntax=docker/dockerfile:1
# Compiled language: build the artifact in a full toolchain image, ship it on a minimal base.
FROM golang:1.22 AS build
WORKDIR /src
COPY . .
RUN go mod download
RUN CGO_ENABLED=0 go build -o /out/server ./cmd/server

FROM gcr.io/distroless/static-debian12
COPY --from=build /out/server /server
EXPOSE 8080
ENTRYPOINT ["/server"]
