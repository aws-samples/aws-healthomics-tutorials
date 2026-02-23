// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

package com.amazon.vincent.job.models

import com.amazon.vincent.job.models.exceptions.VincentInternalException
import spray.json.DefaultJsonProtocol._
import spray.json._

case class AnnotationFields(vep: Option[String] = None)

object AnnotationFields {
  val vepFieldName = "VEP"

  def fromJsonString(jsonStr: String): AnnotationFields = {
    if (jsonStr.trim.isEmpty) {
      new AnnotationFields(None)
    } else {
      parseJson(jsonStr)
    }
  }

  private def parseJson(str: String): AnnotationFields = {
    val vepField = convertToMap(str).getOrElse(AnnotationFields.vepFieldName, "").trim
    if (vepField.isEmpty) {
      new AnnotationFields(None)
    } else {
      AnnotationFields(Some(vepField))
    }
  }

  private def convertToMap(jsonStr: String): Map[String, String] = {
    try {
      jsonStr.parseJson.convertTo[Map[String, String]]
    } catch {
      case e: RuntimeException =>
        throw new VincentInternalException(
          s"Failed to parse Annotation fields parameter: $jsonStr. $e")
    }
  }

}
