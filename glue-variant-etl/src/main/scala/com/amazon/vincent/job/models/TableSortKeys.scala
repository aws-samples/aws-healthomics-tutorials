// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

package com.amazon.vincent.job.models

import com.amazon.vincent.job.models.exceptions.VincentInternalException
import spray.json.DefaultJsonProtocol._
import spray.json._

case class TableSortKeys(sortKeys: Option[String] = None)

object TableSortKeys {
  def fromJsonString(jsonStr: String): List[String] = {
    if (jsonStr.trim.isEmpty) {
      Nil
    } else {
      parseJson(jsonStr)
    }
  }

  private def parseJson(jsonStr: String): List[String] = {
    try {
      jsonStr.parseJson.convertTo[List[String]]
    } catch {
      case e: RuntimeException =>
        throw new VincentInternalException(
          s"Failed to parse Table Sort Keys parameter: $jsonStr. $e")
    }
  }
}
