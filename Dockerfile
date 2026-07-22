FROM eclipse-temurin:25
COPY demo/connector-configs/edc-samples-connector.jar /app/connector.jar
ENTRYPOINT ["java", "-Dedc.fs.config=/app/config.properties", "-jar", "/app/connector.jar"]
