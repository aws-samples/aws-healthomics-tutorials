// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

package com.amazon.vincent.job.logger

trait LoggerTrait {
  def info(m: String): Unit
  def error(m: String): Unit
  def warn(m: String): Unit
}

class VincentGlueLogger extends LoggerTrait {
  // Make the log field transient so that objects with Logging can
  // be serialized and used on another machine
  import com.amazonaws.services.glue.log.GlueLogger
  @transient protected lazy val logger: GlueLogger = new GlueLogger()

  override def info(m: String): Unit = logger.info(m)

  override def error(m: String): Unit = logger.error(m)

  override def warn(m: String): Unit = logger.warn(m)
}
